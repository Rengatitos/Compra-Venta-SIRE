"""Clasificación contable de los comprobantes guardados.

Traduce un comprobante de Mongo a la entrada del motor RAG + Gemini
(`app/services/clasificador`), lo clasifica y guarda el resultado en el propio
comprobante, en `clasificacion_contable`. De ahí lo leen la respuesta del
comprobante y la exportación a Excel, que escribe la cuenta base sólo cuando
el clasificador no pide revisión.

El motor recibe hechos, no una preclasificación: los ítems del detalle SUNAT
(o, a falta de ellos, la glosa), los importes, el tipo de comprobante y las
actividades económicas (CIIU) de la empresa y de la contraparte. Esas
actividades salen de la ficha RUC de SUNAT (`ficha_ruc_service`): la de la
empresa se guarda en ella la primera vez que hace falta, y las de las
contrapartes quedan en caché.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.domain import rubro
from app.domain.comprobante import Libro, normalizar_monto
from app.domain.glosa_similar import clave, palabras, similitud
from app.repositories import clasificaciones_frecuentes as repo_frecuentes
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import empresas as repo_empresas
from app.services import ficha_ruc_service, plan_contable
from app.services.clasificador.motor import MotorNoDisponible, motor
from app.services.clasificador.schemas import (
    ClassificationResponse,
    ClassifyRequest,
    CompanyContext,
    Counterparty,
    EconomicActivity,
    PeriodContext,
    Voucher,
    VoucherItem,
    VoucherType,
)
from app.services.comprobante_service import serializar
from app.services.glosa import ESTADO_CON_GLOSA, estado_glosa, obtener_glosa
from app.services.jobs_service import Reportador
from app.services.sunat.ficha_ruc import es_ruc

logger = logging.getLogger(__name__)

__all__ = ["MotorNoDisponible", "clasificar_comprobante", "clasificar_periodo"]


class SinDescripcion(ValueError):
    """El comprobante no trae ítems ni glosa: no hay operación que clasificar."""


def _numero(valor: Any) -> float | None:
    if valor in (None, ""):
        return None
    return float(normalizar_monto(valor))


def _actividades(empresa: dict[str, Any] | None) -> list[EconomicActivity]:
    """Actividades registradas; si no hay, el CIIU principal del token SUNAT.

    `empresa` es un documento de empresa o el contexto de una ficha RUC
    (`ficha_ruc_service.contexto_de`), que tienen la misma forma.
    """
    if not empresa:
        return []
    registradas = [
        a for a in empresa.get("actividades_economicas") or []
        if isinstance(a, dict) and a.get("ciiu")
    ]
    # La empresa puede elegir qué actividad manda al clasificar (un restaurante
    # cuya ficha SUNAT dice «venta de electrodomésticos»). Esa va primero y como
    # PRINCIPAL; las demás quedan de contexto, como SECUNDARIA.
    elegida = empresa.get("ciiu_principal_clasificacion")
    if elegida and any(a["ciiu"] == elegida for a in registradas):
        registradas.sort(key=lambda a: a["ciiu"] != elegida)
        actividades = [
            EconomicActivity(
                tipo="PRINCIPAL" if a["ciiu"] == elegida else "SECUNDARIA",
                ciiu_v4=a["ciiu"],
                descripcion=(
                    f"{a.get('descripcion') or ''} (actividad principal del negocio, "
                    "elegida por la empresa para clasificar)"
                    if a["ciiu"] == elegida else a.get("descripcion")
                ),
            )
            for a in registradas
        ]
    else:
        actividades = [
            EconomicActivity(
                tipo=a.get("tipo"), ciiu_v4=a["ciiu"], descripcion=a.get("descripcion")
            )
            for a in registradas
        ]
    if actividades:
        return actividades
    ciiu = rubro.ciiu_desde_token_sunat(empresa.get("sunat_token") or "")
    return [EconomicActivity(tipo="PRINCIPAL", ciiu_v4=ciiu)] if ciiu else []


def _ficha(contexto: dict[str, Any] | None) -> dict[str, Any]:
    return (contexto or {}).get("ficha_ruc") or {}


def _items(visible: dict[str, Any]) -> list[VoucherItem]:
    items = [
        VoucherItem(
            descripcion=item["descripcion"].strip(),
            codigo=str(item.get("codigo") or "").strip() or None,
            cantidad=_numero(item.get("cantidad")),
            unidad_medida=str(item.get("unidad_medida") or "").strip() or None,
            valor_unitario=_numero(item.get("valor_unitario")),
            precio_unitario=_numero(item.get("precio_unitario")),
            valor_venta=_numero(item.get("valor_venta")),
        )
        for item in visible.get("detalle_sunat") or []
        if isinstance(item, dict) and str(item.get("descripcion") or "").strip()
    ]
    if items:
        return items
    # Sin ítems, la glosa (manual o sacada de la leyenda) describe la operación.
    glosa = (visible.get("glosa") or "").strip()
    return [VoucherItem(descripcion=glosa)] if glosa else []


def construir_solicitud(
    documento: dict[str, Any],
    empresa: dict[str, Any],
    contraparte: dict[str, Any] | None = None,
) -> ClassifyRequest:
    """Entrada del clasificador para un comprobante de Mongo.

    `contraparte` es la empresa registrada con el RUC de la contraparte o el
    contexto de su ficha RUC, si lo hay: sus actividades ayudan a interpretar
    la operación.
    """
    visible = serializar(documento)
    items = _items(visible)
    if not items:
        raise SinDescripcion(
            f"El comprobante {visible['serie_numero']} no tiene ítems ni glosa que clasificar"
        )

    libro = str(visible["libro"]).upper()
    fecha = visible.get("fecha_emision")
    ficha_empresa = _ficha(empresa)
    ficha_contraparte = _ficha(contraparte)
    return ClassifyRequest(
        empresa=CompanyContext(
            ruc=empresa["ruc"],
            razon_social=empresa.get("nombre") or ficha_empresa.get("razon_social"),
            actividades_economicas=_actividades(empresa),
            comprobantes_autorizados_impresion=ficha_empresa.get("comprobantes_autorizados") or [],
            sistema_emision_electronica=[
                {"descripcion": s} for s in ficha_empresa.get("sistema_emision_electronica") or []
            ],
            emisor_electronico_desde=ficha_empresa.get("emisor_electronico_desde") or None,
            comprobantes_electronicos=ficha_empresa.get("comprobantes_electronicos") or [],
        ),
        contexto_periodo=PeriodContext(periodo=documento.get("periodo"), libro=libro),
        comprobante=Voucher(
            libro=libro,
            tipo_cp=VoucherType(
                codigo=visible["tipo_cp"], descripcion=visible["tipo_cp_descripcion"]
            ),
            serie=visible["serie"],
            numero=visible["numero"],
            fecha_emision=fecha.isoformat() if fecha else None,
            contraparte=Counterparty(
                tipo_documento=visible.get("tipo_doc_identidad") or None,
                numero_documento=visible.get("documento_contraparte") or None,
                razon_social=visible.get("razon_social") or None,
                actividades_economicas=_actividades(contraparte),
                comprobantes_autorizados=ficha_contraparte.get("comprobantes_autorizados") or [],
                sistema_emision_electronica=[
                    {"descripcion": s}
                    for s in ficha_contraparte.get("sistema_emision_electronica") or []
                ],
            ),
            moneda=visible.get("moneda"),
            origen=str(visible.get("origen") or "").upper(),
            importes={
                campo: visible.get(campo)
                for campo in (
                    "base_imponible", "igv", "exonerado", "inafecto",
                    "no_gravado", "icbper", "otros_tributos", "total",
                )
            },
        ),
        items=items,
    )


def a_documento(respuesta: ClassificationResponse, modelo: str) -> dict[str, Any]:
    def cuenta(valor):
        return valor.model_dump() if valor else None

    return {
        "cuenta_base": cuenta(respuesta.cuenta_base_imponible),
        "cuenta_total": cuenta(respuesta.cuenta_total),
        "clasificacion": respuesta.clasificacion,
        "subtipo": respuesta.subtipo,
        "condicion_igv": respuesta.condicion_igv,
        "centro_costos": respuesta.centro_costos,
        "confianza": respuesta.confianza,
        "confianza_rag": respuesta.confianza_rag,
        "requiere_revision": respuesta.requiere_revision,
        "razon": respuesta.razon,
        "modelo": modelo,
        "clasificado_en": datetime.now(UTC),
    }


async def _asegurar_actividades_empresa(db, empresa: dict) -> dict:
    """La empresa con sus actividades; si no tiene, las trae de su ficha RUC.

    Un fallo de SUNAT no impide clasificar: se sigue con el CIIU del token.
    """
    if empresa.get("actividades_economicas"):
        return empresa
    try:
        return await ficha_ruc_service.actualizar_empresa(db, empresa)
    except Exception as exc:
        logger.warning("Sin ficha RUC para la empresa %s: %s", empresa.get("ruc"), exc)
        return empresa


async def contextos_contrapartes(
    db, empresa: dict, documentos: list[dict], consultar_faltantes: bool
) -> dict[str, dict]:
    """Contexto de cada contraparte con RUC, por RUC.

    Primero la empresa registrada con ese RUC (si tiene actividades); si no,
    su ficha RUC, de la caché o —con `consultar_faltantes`— de SUNAT.
    """
    rucs = {str(d.get("documento_contraparte") or "").strip() for d in documentos}
    rucs = {r for r in rucs if es_ruc(r) and r != empresa.get("ruc")}
    contextos: dict[str, dict] = {}
    for ruc in rucs:
        registrada = await repo_empresas.obtener_por_ruc(db, ruc)
        if registrada and registrada.get("actividades_economicas"):
            contextos[ruc] = registrada
    try:
        fichas = await ficha_ruc_service.obtener_varias(
            db, sorted(rucs - set(contextos)), consultar_faltantes=consultar_faltantes
        )
    except Exception as exc:
        logger.warning("No se pudieron consultar las fichas RUC de las contrapartes: %s", exc)
        fichas = {}
    for ruc, ficha in fichas.items():
        contextos[ruc] = ficha_ruc_service.contexto_de(ficha)
    return contextos


class Memoria:
    """Clasificaciones frecuentes confiables de una empresa y libro, en memoria.

    Se carga una vez por trabajo y crece con lo que la IA va clasificando bien:
    así el tercer «SACOS DE PAPA» de un mismo lote ya no llama a Gemini.
    """

    def __init__(self, entradas: list[dict[str, Any]]):
        self._entradas = [(palabras(e.get("glosa") or e.get("clave")), e) for e in entradas]
        # Glosas en las que la IA no dio cuenta en este trabajo: cuántas veces
        # y el último resultado, para dejar de insistir al llegar al tope.
        self._fallidos: dict[str, tuple[int, dict[str, Any]]] = {}

    def fallo(self, clave_glosa: str, resultado: dict[str, Any]) -> None:
        intentos = self._fallidos.get(clave_glosa, (0, {}))[0] + 1
        self._fallidos[clave_glosa] = (intentos, resultado)

    def agotada(self, clave_glosa: str) -> tuple[int, dict[str, Any]] | None:
        """El último fallo, si esa glosa ya gastó sus intentos con la IA."""
        registro = self._fallidos.get(clave_glosa)
        if registro and registro[0] >= settings.CLASIFICADOR_INTENTOS_POR_GLOSA:
            return registro
        return None

    @classmethod
    async def cargar(cls, db, empresa_id: str, libro: str) -> Memoria:
        return cls(await repo_frecuentes.listar(db, empresa_id, libro, solo_confiables=True))

    def buscar(self, glosa: str) -> tuple[dict[str, Any], float] | None:
        buscadas = palabras(glosa)
        mejor = max(
            ((entrada, similitud(buscadas, suyas)) for suyas, entrada in self._entradas),
            key=lambda par: par[1],
            default=None,
        )
        if mejor and mejor[1] >= settings.CLASIFICADOR_SIMILITUD_MINIMA:
            return mejor
        return None

    def agregar(self, entrada: dict[str, Any]) -> None:
        self._entradas.append((palabras(entrada.get("glosa")), entrada))


def _condicion_igv(visible: dict[str, Any]) -> str:
    """La misma regla determinista que usa el motor (`ClassifierService._amount_condition`)."""
    if visible.get("exonerado", 0) > 0:
        return "EXONERADO"
    if visible.get("inafecto", 0) > 0:
        return "INAFECTO"
    if visible.get("no_gravado", 0) > 0:
        return "NO_GRAVADO"
    if visible.get("igv", 0) > 0 or visible.get("base_imponible", 0) > 0:
        return "GRAVADO"
    return "NO_DETERMINADA"


# El motivo de la IA mezcla el porqué (qué es la operación, cómo encaja en el
# negocio y por qué esa cuenta) con el rastro técnico del RAG: frases
# «Evidencia …: archivo.xlsx.». Esas se quitan; el porqué se queda entero.
_EVIDENCIA = re.compile(
    r"\s*Evidencia (?:contextual RAG|cuenta base|cuenta total):.*?\.(?=\s|$)"
)
MAX_POR_QUE = 900
SIN_POR_QUE = (
    "El razonamiento original de la IA no quedó registrado (se clasificó antes de que se "
    "guardara). «Volver a clasificar con IA» en un comprobante con esta glosa lo registra."
)


def resumir_motivo(razon: str | None) -> str:
    """El porqué de una clasificación de la IA, sin el rastro técnico del RAG."""
    texto = re.sub(r"\s+", " ", _EVIDENCIA.sub("", razon or "")).strip()
    if len(texto) > MAX_POR_QUE:
        corte = texto.rfind(". ", 0, MAX_POR_QUE)
        texto = texto[: corte + 1] if corte > 0 else texto[:MAX_POR_QUE].rstrip() + "…"
    return texto


def componer_motivo(
    jerarquia_base: list[dict[str, Any]],
    jerarquia_total: list[dict[str, Any]],
    por_que: str,
    *,
    confirmada: bool = False,
    reutilizado: str | None = None,
) -> str:
    """El motivo que se guarda y se muestra: qué es la cuenta según el plan y por qué.

    Siempre con la misma forma, venga la clasificación de la IA, de una
    clasificación frecuente o de una corrección, para que se lea igual en el
    panel, en el Excel y en el PDF.
    """
    partes = []
    if jerarquia_base:
        partes.append(
            f"Cuenta base {jerarquia_base[-1]['codigo']} según el plan de cuentas: "
            f"{plan_contable.texto_jerarquia(jerarquia_base)}."
        )
    else:
        partes.append(
            "Sin cuenta base: ninguna cuenta del plan recuperada sustenta la operación, "
            "requiere revisión."
        )
    if jerarquia_total:
        partes.append(
            f"Cuenta total {jerarquia_total[-1]['codigo']}: "
            f"{plan_contable.texto_jerarquia(jerarquia_total)}."
        )
    partes.append(f"Por qué: {por_que or SIN_POR_QUE}")
    if confirmada:
        partes.append("Cuenta confirmada por un usuario en Clasificaciones frecuentes.")
    if reutilizado:
        partes.append(reutilizado)
    return " ".join(partes)


async def completar_motivo(
    db,
    empresa_id: str,
    resultado: dict[str, Any],
    por_que: str,
    *,
    confirmada: bool = False,
    reutilizado: str | None = None,
) -> dict[str, Any]:
    """Añade al resultado el motivo compuesto y sus partes, para guardarlos.

    Las partes van también por separado (`jerarquia_base`, `jerarquia_total`,
    `motivo_ia`, `reutilizado`) para que el panel las presente ordenadas.
    """
    for campo in ("cuenta_base", "cuenta_total"):
        cuenta = resultado.get(campo) or {}
        camino = await plan_contable.jerarquia(db, empresa_id, cuenta.get("codigo"))
        resultado[f"jerarquia_{campo.split('_')[1]}"] = camino
        # La descripción de la cuenta, la del plan si la IA no la trajo.
        if cuenta and not cuenta.get("descripcion") and camino and camino[-1].get("descripcion"):
            resultado[campo] = {**cuenta, "descripcion": camino[-1]["descripcion"]}
    resultado["motivo_ia"] = por_que or SIN_POR_QUE
    resultado["reutilizado"] = reutilizado
    resultado["razon"] = componer_motivo(
        resultado["jerarquia_base"],
        resultado["jerarquia_total"],
        por_que,
        confirmada=confirmada,
        reutilizado=reutilizado,
    )
    return resultado


async def desde_memoria(
    db, empresa_id: str, entrada: dict[str, Any], coincidencia: float, documento: dict
) -> dict[str, Any]:
    """Clasificación de un comprobante a partir de una clasificación frecuente."""
    de_usuario = entrada.get("origen") == "usuario"
    resultado = {
        "cuenta_base": entrada.get("cuenta_base"),
        "cuenta_total": entrada.get("cuenta_total"),
        "clasificacion": entrada.get("clasificacion", ""),
        "subtipo": entrada.get("subtipo", ""),
        # La condición de IGV es de cada comprobante, no de la glosa.
        "condicion_igv": _condicion_igv(serializar(documento)),
        "centro_costos": None,
        "confianza": 1.0 if de_usuario else round(float(entrada.get("confianza") or 0.0), 4),
        "confianza_rag": 0.0,
        "requiere_revision": False,
        "razon_ia": entrada.get("razon") or "",
        "modelo": "memoria",
        "origen": "memoria",
        "memoria_id": str(entrada["_id"]),
        "clasificado_en": datetime.now(UTC),
    }
    return await completar_motivo(
        db,
        empresa_id,
        resultado,
        resumir_motivo(entrada.get("razon")),
        confirmada=de_usuario,
        reutilizado=(
            f"También reutilizado: misma glosa que «{entrada.get('glosa', '')}» "
            f"({coincidencia:.0%} de coincidencia), sin volver a consultar a la IA."
        ),
    )


async def propagar_a_revisiones(db, empresa_id: str, libro: str, entrada: dict[str, Any]) -> int:
    """Aplica una clasificación confiable a los comprobantes con glosa equivalente
    que estaban en «Requiere revisión», de cualquier periodo.

    Es lo que cierra el ciclo cuando la IA falla con una glosa y acierta con
    otra igual más tarde: los que habían quedado sin cuenta la reciben, con el
    motivo completo, sin volver a consultar a la IA.
    """
    suyas = palabras(entrada.get("glosa"))
    if not suyas:
        return 0
    actualizados = 0
    for doc in await repo_comprobantes.listar_que_requieren_revision(db, empresa_id, libro):
        parecido = similitud(palabras(obtener_glosa(doc)), suyas)
        if parecido < settings.CLASIFICADOR_SIMILITUD_MINIMA:
            continue
        resultado = await desde_memoria(db, empresa_id, entrada, parecido, doc)
        await repo_comprobantes.guardar_clasificacion(db, doc["_id"], resultado)
        await repo_frecuentes.contar_uso(db, entrada["_id"])
        actualizados += 1
    if actualizados:
        logger.info(
            "Glosa «%s»: %s comprobantes en revisión recibieron la cuenta %s",
            entrada.get("glosa"), actualizados, (entrada.get("cuenta_base") or {}).get("codigo"),
        )
    return actualizados


async def _clasificar(
    db, empresa, documento, contextos: dict[str, dict], memoria: Memoria | None = None
) -> dict[str, Any]:
    glosa = obtener_glosa(documento)
    clave_glosa = clave(glosa) if glosa else ""
    empresa_id = str(empresa["_id"])
    libro = documento.get("libro", "")

    if memoria is not None and glosa:
        encontrada = memoria.buscar(glosa)
        if encontrada:
            entrada, coincidencia = encontrada
            resultado = await desde_memoria(db, empresa_id, entrada, coincidencia, documento)
            await repo_comprobantes.guardar_clasificacion(db, documento["_id"], resultado)
            await repo_frecuentes.contar_uso(db, entrada["_id"])
            return resultado
        # Con glosas en las que la IA ya falló varias veces en este trabajo no
        # se sigue pagando: queda en revisión con el último intento.
        agotada = memoria.agotada(clave_glosa) if clave_glosa else None
        if agotada:
            intentos, ultimo = agotada
            resultado = {**ultimo, "clasificado_en": datetime.now(UTC)}
            por_que = ultimo.get("motivo_ia") or ""
            await completar_motivo(
                db, empresa_id, resultado, por_que,
                reutilizado=(
                    f"La IA no encontró cuenta para esta glosa en {intentos} comprobantes de "
                    "este trabajo; no se volvió a consultar. Recibirá la cuenta en cuanto la "
                    "IA acierte con otro igual o se corrija en Clasificaciones frecuentes."
                ),
            )
            await repo_comprobantes.guardar_clasificacion(db, documento["_id"], resultado)
            return resultado

    ruc_contraparte = str(documento.get("documento_contraparte") or "").strip()
    solicitud = construir_solicitud(documento, empresa, contextos.get(ruc_contraparte))
    # El motor es síncrono (embeddings en CPU y llamadas bloqueantes a
    # Gemini): en el hilo del loop congelaría la API entera.
    clasificador = await asyncio.to_thread(motor.obtener)
    respuesta = await asyncio.to_thread(clasificador.classify, solicitud)
    resultado = a_documento(respuesta, motor.settings.gemini_model)
    resultado["origen"] = "ia"
    # El texto íntegro de la IA se conserva (`razon_ia`); `razon` pasa a ser el
    # motivo compuesto con el plan de cuentas.
    resultado["razon_ia"] = resultado["razon"]
    await completar_motivo(db, empresa_id, resultado, resumir_motivo(resultado["razon_ia"]))

    # Toda clasificación de la IA queda en las frecuentes, también las dudosas:
    # así el usuario las ve ahí y, si corrige una, la corrección vale para los
    # comprobantes que la comparten. Solo las confiables se reutilizan.
    entrada = None
    if clave_glosa:
        entrada_id = await repo_frecuentes.registrar_de_ia(
            db, empresa_id, libro, clave_glosa, glosa, resultado
        )
        resultado["memoria_id"] = str(entrada_id)
        entrada = {**resultado, "_id": entrada_id, "glosa": glosa, "razon": resultado["razon_ia"]}
    await repo_comprobantes.guardar_clasificacion(db, documento["_id"], resultado)

    if entrada is not None and not resultado["requiere_revision"]:
        # Acierto: se reutiliza en adelante y se lleva a los que la esperaban.
        if memoria is not None:
            memoria.agregar(entrada)
        resultado["propagados"] = await propagar_a_revisiones(db, empresa_id, libro, entrada)
    elif memoria is not None and clave_glosa:
        memoria.fallo(clave_glosa, resultado)
    return resultado


async def clasificar_comprobante(
    db, empresa: dict, documento: dict, usar_memoria: bool = True
) -> dict[str, Any]:
    """Clasifica un comprobante y guarda el resultado. Propaga `SinDescripcion`.

    Con `usar_memoria=False` (el «Volver a clasificar» de la ficha) va siempre
    a la IA, aunque haya una clasificación frecuente que coincida.
    """
    empresa = await _asegurar_actividades_empresa(db, empresa)
    memoria = (
        await Memoria.cargar(db, str(empresa["_id"]), documento.get("libro", ""))
        if usar_memoria else None
    )
    contextos: dict[str, dict] = {}
    if memoria is None or not memoria.buscar(obtener_glosa(documento)):
        contextos = await contextos_contrapartes(
            db, empresa, [documento], consultar_faltantes=True
        )
    return await _clasificar(db, empresa, documento, contextos, memoria)


async def clasificar_periodo(
    db,
    empresa: dict,
    periodo: str,
    libro: Libro,
    reportar: Reportador,
    reclasificar: bool = False,
) -> dict[str, Any]:
    empresa_id = str(empresa["_id"])
    pendientes = await repo_comprobantes.listar_para_clasificar(
        db, empresa_id, periodo, libro, reclasificar
    )
    # Solo los comprobantes «con glosa», con la misma regla que la columna
    # «Estado glosa»: sin descripción de la operación, lo que saliera sería una
    # cuenta adivinada. Los demás esperan a que se complete la glosa.
    con_glosa = [d for d in pendientes if estado_glosa(d) == ESTADO_CON_GLOSA]
    documentos = con_glosa[: settings.CLASIFICADOR_MAX_COMPROBANTES]
    total = len(documentos)
    # Antes de nada: si el motor no arranca, que el trabajo falle con ese
    # motivo y no con un error repetido por cada comprobante.
    await reportar(0, total, "Cargando el clasificador contable")
    await asyncio.to_thread(motor.obtener)

    memoria = await Memoria.cargar(db, empresa_id, libro.value)
    await reportar(0, total, "Consultando actividades económicas (CIIU) en SUNAT")
    empresa = await _asegurar_actividades_empresa(db, empresa)
    # Solo hace falta el CIIU de las contrapartes que irán a la IA.
    para_ia = [d for d in documentos if not memoria.buscar(obtener_glosa(d))]
    contextos = await contextos_contrapartes(
        db, empresa, para_ia, settings.CLASIFICADOR_CONSULTAR_CONTRAPARTES
    )

    conteo = {
        "clasificados": 0, "reutilizados": 0, "propagados": 0, "requieren_revision": 0,
        "sin_descripcion": 0, "errores": 0,
    }
    errores: list[dict[str, str]] = []
    for i, documento in enumerate(documentos, start=1):
        serie_numero = documento.get("serie_numero", "")
        await reportar(i - 1, total, f"Clasificando {serie_numero}")
        try:
            resultado = await _clasificar(db, empresa, documento, contextos, memoria)
        except SinDescripcion:
            conteo["sin_descripcion"] += 1
            continue
        except Exception as exc:
            # Un fallo de Gemini en un comprobante no tumba el lote: queda sin
            # clasificar y entra en la siguiente vuelta.
            logger.warning("No se pudo clasificar %s: %s", serie_numero, exc)
            conteo["errores"] += 1
            errores.append({"serie_numero": serie_numero, "error": str(exc)[:300]})
            continue
        conteo["clasificados"] += 1
        conteo["reutilizados"] += int(resultado.get("origen") == "memoria")
        conteo["propagados"] += resultado.get("propagados", 0)
        conteo["requieren_revision"] += int(resultado["requiere_revision"])

    await reportar(total, total, "Clasificación terminada")
    # Los que el tope dejó fuera, más los que fallaron: entran en otra vuelta.
    restantes = len(con_glosa) - total + conteo["errores"]
    return {
        **conteo,
        # Pendientes del libro que no se tocaron por no tener glosa todavía.
        "sin_glosa_omitidos": len(pendientes) - len(con_glosa),
        "contrapartes_con_ciiu": len(contextos),
        "pendientes_restantes": restantes,
        "detalle_errores": errores[:20],
    }


async def aplicar_correccion(db, empresa_id: str, entrada: dict[str, Any]) -> int:
    """Lleva una clasificación frecuente corregida a los comprobantes que la usaban."""
    campos = await completar_motivo(
        db,
        empresa_id,
        {
            "cuenta_base": entrada.get("cuenta_base"),
            "cuenta_total": entrada.get("cuenta_total"),
            "requiere_revision": False,
            "origen": "memoria",
            "modelo": "memoria",
            "razon_ia": entrada.get("razon") or "",
            "clasificado_en": datetime.now(UTC),
        },
        resumir_motivo(entrada.get("razon")),
        confirmada=True,
    )
    enlazados = await repo_comprobantes.aplicar_clasificacion_frecuente(
        db, empresa_id, str(entrada["_id"]), campos
    )
    return enlazados + await propagar_a_revisiones(db, empresa_id, entrada["libro"], entrada)


def estado_motor() -> dict[str, Any]:
    return {
        "habilitado": settings.CLASIFICADOR_HABILITADO,
        **motor.describir(),
    }
