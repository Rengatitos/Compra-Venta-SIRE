"""Lote de clasificación: solo con glosa, y sin volver a pagar a la IA lo que ya sabe.

Caso real que lo motivó: un restaurante compra papa y zanahoria cada semana
(«SACOS DE PAPA DE PRIMERA / SACOS DE ZANAHORIA DE PRIMERA» y «SACOS DE PAPA /
SACOS DE ZANAHORIA PRIMERA»). La primera la clasificó bien la IA; la segunda,
con la misma operación, salió sin cuenta.
"""

from __future__ import annotations

import asyncio

import pytest

from app.domain.comprobante import Libro
from app.domain.glosa_similar import clave, palabras, similitud
from app.repositories.comprobantes import a_documento
from app.services import clasificacion_service
from app.services.clasificacion_service import _actividades
from app.services.clasificador.schemas import ClassificationResponse
from app.services.sunat.propuesta import a_comprobante

PAYLOAD = {
    "numSerieCDP": "E001", "numCDP": "1169", "codTipoCDP": "01",
    "numDocIdentidadProveedor": "20611455802", "fecEmision": "2026-08-07",
    "montos": {"mtoValorAdqNG": 535.0, "mtoTotalCp": 535.0},
}
EMPRESA = {
    "_id": "empresa1", "ruc": "10209911031",
    "actividades_economicas": [
        {"tipo": "PRINCIPAL", "ciiu": "4759", "descripcion": "VENTA DE ELECTRODOMESTICOS",
         "origen": "sunat"},
        {"tipo": "SECUNDARIA", "ciiu": "5320", "descripcion": "MENSAJERIA", "origen": "sunat"},
        {"tipo": None, "ciiu": "5610", "descripcion": "RESTAURANTES", "origen": "manual"},
    ],
    "ciiu_principal_clasificacion": "5610",
}


def _doc(numero: str, glosa: str | None = None, **extra) -> dict:
    documento = a_documento(a_comprobante(PAYLOAD, Libro.COMPRAS), "empresa1", "202608")
    documento.update({"_id": numero, "numero": numero, "serie_numero": f"E001-{numero}"})
    if glosa:
        documento["detalle_sunat"] = [{"descripcion": d} for d in glosa.split(" / ")]
    return {**documento, **extra}


def test_las_glosas_de_la_misma_compra_coinciden():
    a = palabras("SACOS DE PAPA DE PRIMERA / SACOS DE ZANAHORIA DE PRIMERA")
    b = palabras("SACOS DE PAPA / SACOS DE ZANAHORIA PRIMERA")
    assert similitud(a, b) == 1.0
    assert clave("Sacos de papa") == clave("SACOS  DE  PAPÁ")
    # El mes y el año de un recibo no cambian la operación.
    assert similitud(palabras("INTERNET DUO JULIO 2026"), palabras("INTERNET DUO AGOSTO 2026")) == 1
    # Otra mercadería sí.
    assert similitud(palabras("SACOS DE PAPA"), palabras("SACOS DE ARROZ")) < 0.8


def test_la_actividad_elegida_manda_al_clasificar():
    actividades = _actividades(EMPRESA)
    assert [(a.tipo, a.ciiu_v4) for a in actividades] == [
        ("PRINCIPAL", "5610"), ("SECUNDARIA", "4759"), ("SECUNDARIA", "5320"),
    ]
    assert "elegida por la empresa" in actividades[0].descripcion


class Frecuentes:
    """Colección `clasificaciones_frecuentes` en memoria."""

    def __init__(self):
        self.entradas: dict[str, dict] = {}
        self.usos: list[str] = []

    async def listar(self, db, empresa_id, libro=None, solo_confiables=False):
        return [e for e in self.entradas.values() if e["confiable"] or not solo_confiables]

    async def registrar_de_ia(self, db, empresa_id, libro, clave_, glosa, clasificacion):
        nueva = {"_id": f"m{len(self.entradas)}", "glosa": glosa}
        entrada = self.entradas.setdefault(clave_, nueva)
        entrada.update(
            cuenta_base=clasificacion["cuenta_base"], cuenta_total=clasificacion["cuenta_total"],
            confianza=clasificacion["confianza"], origen="ia", razon=clasificacion["razon_ia"],
            confiable=not clasificacion["requiere_revision"],
        )
        return entrada["_id"]

    async def contar_uso(self, db, entrada_id):
        self.usos.append(entrada_id)


def _respuesta(cuenta: str | None) -> ClassificationResponse:
    return ClassificationResponse(
        clasificacion="COMPRA", subtipo="MATERIAS PRIMAS",
        cuenta_base_imponible=(
            {"codigo": cuenta, "descripcion": "MATERIAS PRIMAS"} if cuenta else None
        ),
        cuenta_total={"codigo": "4212", "descripcion": "EMITIDAS"},
        condicion_igv="NO_GRAVADO", confianza=0.73, razon="Insumo del restaurante.",
        requiere_revision=cuenta is None, confianza_rag=0.7,
    )


@pytest.fixture
def entorno(monkeypatch):
    frecuentes = Frecuentes()
    guardados: dict[str, dict] = {}
    a_la_ia: list[str] = []
    documentos: dict[str, dict] = {}

    async def guardar(db, documento_id, clasificacion):
        guardados[documento_id] = clasificacion

    async def en_revision(db, empresa_id, libro):
        return [
            {**documentos[i], "clasificacion_contable": c}
            for i, c in guardados.items() if c["requiere_revision"]
        ]

    async def nada(*args, **kwargs):
        return None

    async def sin_fichas(db, rucs, consultar_faltantes=True):
        return {}

    class Clasificador:
        def classify(self, solicitud):
            numero = solicitud.comprobante.numero
            a_la_ia.append(numero)
            if numero == "9":
                raise RuntimeError("GEMINI_API_ERROR: 503")
            descripciones = " ".join(i.descripcion for i in solicitud.items)
            return _respuesta("6021024" if "PAPA" in descripciones else None)

    class Motor:
        settings = type("S", (), {"gemini_model": "gemini-x"})()

        def obtener(self):
            return Clasificador()

    for nombre in ("listar", "registrar_de_ia", "contar_uso"):
        monkeypatch.setattr(clasificacion_service.repo_frecuentes, nombre,
                            getattr(frecuentes, nombre))
    monkeypatch.setattr(clasificacion_service.repo_comprobantes, "guardar_clasificacion", guardar)
    monkeypatch.setattr(
        clasificacion_service.repo_comprobantes, "listar_que_requieren_revision", en_revision
    )
    monkeypatch.setattr(clasificacion_service.repo_empresas, "obtener_por_ruc", nada)
    monkeypatch.setattr(clasificacion_service.ficha_ruc_service, "obtener_varias", sin_fichas)
    monkeypatch.setattr(clasificacion_service, "motor", Motor())
    return frecuentes, guardados, a_la_ia, documentos


def _lote(monkeypatch, entorno, documentos):
    entorno[3].update({d["_id"]: d for d in documentos})

    async def listar(*args, **kwargs):
        return documentos

    async def reportar(*args, **kwargs):
        pass

    monkeypatch.setattr(clasificacion_service.repo_comprobantes, "listar_para_clasificar", listar)
    return asyncio.run(clasificacion_service.clasificar_periodo(
        None, EMPRESA, "202608", Libro.COMPRAS, reportar
    ))


def test_la_misma_compra_no_vuelve_a_la_ia(monkeypatch, entorno):
    frecuentes, guardados, a_la_ia, _ = entorno
    resultado = _lote(monkeypatch, entorno, [
        _doc("1169", "SACOS DE PAPA DE PRIMERA / SACOS DE ZANAHORIA DE PRIMERA"),
        _doc("1178", "SACOS DE PAPA / SACOS DE ZANAHORIA PRIMERA"),
        _doc("1180", "SACOS DE ZANAHORIA / SACOS DE PAPA DE PRIMERA"),
    ])

    assert a_la_ia == ["1169"]  # solo la primera paga la IA
    assert {g["cuenta_base"]["codigo"] for g in guardados.values()} == {"6021024"}
    assert guardados["1178"]["origen"] == "memoria"
    assert guardados["1178"]["requiere_revision"] is False
    assert guardados["1178"]["condicion_igv"] == "NO_GRAVADO"
    # El motivo dice qué es la cuenta según el plan y por qué, también al reutilizar.
    for numero in ("1169", "1178"):
        motivo = guardados[numero]["razon"]
        assert "Cuenta base 6021024 según el plan de cuentas: 60 COMPRAS › 602 MATERIAS" in motivo
        assert "Cuenta total 4212: 42 CUENTAS POR PAGAR COMERCIALES TERCEROS" in motivo
        assert "Por qué: Insumo del restaurante." in motivo
        assert [c["codigo"] for c in guardados[numero]["jerarquia_base"]] == [
            "60", "602", "6021", "6021024",
        ]
    assert "También reutilizado" not in guardados["1169"]["razon"]  # esta sí fue a la IA
    assert "También reutilizado" in guardados["1178"]["razon"]
    assert guardados["1178"]["motivo_ia"] == "Insumo del restaurante."
    assert resultado["clasificados"] == 3
    assert resultado["reutilizados"] == 2
    assert len(frecuentes.usos) == 2


def test_al_acertar_con_una_glosa_se_actualizan_las_que_estaban_en_revision(
    monkeypatch, entorno
):
    frecuentes, guardados, a_la_ia, _ = entorno
    respuestas = iter([None, "603202521"])  # falla la primera vez, acierta la segunda
    monkeypatch.setattr(
        clasificacion_service.motor.obtener().__class__, "classify",
        lambda self, solicitud: (a_la_ia.append(solicitud.comprobante.numero)
                                 or _respuesta(next(respuestas))),
    )
    resultado = _lote(monkeypatch, entorno, [
        _doc("66929", "DIESEL B5 S50 UV"),
        _doc("67132", "DIESEL B5 S50 UV"),
        _doc("67200", "DIESEL B5 S50 UV"),
    ])

    assert a_la_ia == ["66929", "67132"]  # tras acertar, el tercero ya reutiliza
    assert {g["cuenta_base"]["codigo"] for g in guardados.values()} == {"603202521"}
    assert guardados["66929"]["requiere_revision"] is False  # el que había fallado
    assert "Cuenta base 603202521" in guardados["66929"]["razon"]
    assert resultado["propagados"] == 1
    entrada = frecuentes.entradas[clave("DIESEL B5 S50 UV")]
    assert entrada["confiable"] is True
    assert entrada["cuenta_base"]["codigo"] == "603202521"


def test_con_fallos_seguidos_se_deja_de_consultar_al_tope(monkeypatch, entorno):
    _, guardados, a_la_ia, _ = entorno
    _lote(monkeypatch, entorno, [_doc(str(n), "GAS DOMESTICO 10KG") for n in range(1, 6)])
    # Tope por defecto: tres intentos por glosa; el resto no gasta consultas.
    assert a_la_ia == ["1", "2", "3"]
    assert all(g["requiere_revision"] for g in guardados.values())
    assert "no se volvió a consultar" in guardados["5"]["razon"]


def test_una_clasificacion_dudosa_se_guarda_pero_no_se_reutiliza(monkeypatch, entorno):
    frecuentes, guardados, a_la_ia, _ = entorno
    _lote(monkeypatch, entorno, [
        _doc("1", "DIESEL B5 S50 UV"),
        _doc("2", "DIESEL B5 S50 UV"),
    ])
    # Sin cuenta la IA pide revisión: queda en frecuentes para corregirla, pero
    # la segunda vuelve a la IA en vez de copiar una respuesta dudosa.
    assert a_la_ia == ["1", "2"]
    entrada = frecuentes.entradas[clave("DIESEL B5 S50 UV")]
    assert entrada["confiable"] is False
    assert guardados["2"]["memoria_id"] == entrada["_id"]


def test_solo_con_glosa_y_un_fallo_no_detiene_el_lote(monkeypatch, entorno):
    _, guardados, a_la_ia, _ = entorno
    resultado = _lote(monkeypatch, entorno, [
        _doc("1", "SACOS DE PAPA"),
        _doc("9", "GAS DOMESTICO 10KG"),  # la IA falla en este
        _doc("3"),  # pendiente de consultar en SOL: sin glosa
        _doc("4", glosa_consultada=True),  # consultado y sin glosa
        _doc("5", glosa="Alquiler de local"),  # glosa manual
    ])
    assert a_la_ia == ["1", "9", "5"]  # los sin glosa ni llegan a la IA
    assert set(guardados) == {"1", "5"}
    assert resultado["errores"] == 1
    assert resultado["sin_glosa_omitidos"] == 2
    assert resultado["pendientes_restantes"] == 1
    assert resultado["detalle_errores"][0]["serie_numero"] == "E001-9"


def test_el_porque_se_queda_entero_sin_el_rastro_del_rag():
    razon = (
        "ADQUISICIÓN DE COMBUSTIBLE: El ítem es DIESEL B5 S50 UV, combustible diésel. "
        "Guarda relación con el giro. Evidencia contextual RAG: ciiu/Notas_CIIU_Rev4.pdf. "
        "Se clasifica en suministros de energía (603202523). Evidencia cuenta base: 603202523 "
        "recuperada desde plan_cuentas/cuentas_reporte_compras_RAG.xlsx. Evidencia cuenta "
        "total: 4212 recuperada desde plan_cuentas/PLAN_DE_CUENTAS_CONTASIS.xlsx."
    )
    assert clasificacion_service.resumir_motivo(razon) == (
        "ADQUISICIÓN DE COMBUSTIBLE: El ítem es DIESEL B5 S50 UV, combustible diésel. "
        "Guarda relación con el giro. Se clasifica en suministros de energía (603202523)."
    )


def test_sin_cuenta_ni_porque_se_dice_y_no_se_inventa():
    motivo = clasificacion_service.componer_motivo([], [], "", confirmada=True)
    assert motivo.startswith("Sin cuenta base")
    assert "no quedó registrado" in motivo
    assert "confirmada por un usuario" in motivo


def test_la_jerarquia_sale_del_plan_contasis():
    camino = asyncio.run(clasificacion_service.plan_contable.jerarquia(None, "e", "603202523"))
    assert [(c["codigo"], c["descripcion"]) for c in camino] == [
        ("60", "COMPRAS"),
        ("603", "MATERIALES AUXILIARES,SUMINISTROS Y REPUESTOS"),
        ("6032", "SUMINISTROS"),
        ("603202523", "SUMINISTROS ENERGIA - Compras"),
    ]
    # Un código que no está en el plan se muestra igual, sin descripción.
    assert asyncio.run(
        clasificacion_service.plan_contable.jerarquia(None, "e", "999999")
    )[-1] == {"codigo": "999999", "descripcion": None}
