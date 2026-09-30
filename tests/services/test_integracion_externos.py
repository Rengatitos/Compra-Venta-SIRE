"""Paso de los comprobantes de Apaclla Bot a su periodo.

Corre sobre una base en memoria con la API de Motor que usan los repositorios,
así que también cubre las consultas de `comprobantes`, `comprobantes_externos`
y `periodos`, no sólo el servicio.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128

from app.domain.comprobante import Libro, Origen
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import comprobantes_externos as repo_externos
from app.repositories import periodos as repo_periodos
from app.repositories._mongo import (
    NOMBRE_COL_COMPROBANTES,
    NOMBRE_COL_COMPROBANTES_EXTERNOS,
    NOMBRE_COL_PERIODOS,
)
from app.services import comprobantes_externos_service, integracion_externos, pagos_vouchers

EMPRESA_ID = "65f000000000000000000001"
PERIODO = "202609"

# --- Base en memoria -----------------------------------------------------------


def _casa_valor(valor: Any, condicion: Any, presente: bool) -> bool:
    if isinstance(condicion, dict) and any(k.startswith("$") for k in condicion):
        for operador, argumento in condicion.items():
            if operador == "$in" and valor not in argumento:
                return False
            if operador == "$ne" and valor == argumento:
                return False
            if operador == "$exists" and presente != argumento:
                return False
            if operador == "$gt" and not (valor is not None and valor > argumento):
                return False
        return True
    return valor == condicion


def _casa(documento: dict, filtro: dict) -> bool:
    for clave, condicion in filtro.items():
        if clave == "$or":
            if not any(_casa(documento, f) for f in condicion):
                return False
        elif clave == "$nor":
            if any(_casa(documento, f) for f in condicion):
                return False
        else:
            presente, valor = _campo(documento, clave)
            if not _casa_valor(valor, condicion, presente):
                return False
    return True


def _campo(documento: dict, clave: str) -> tuple[bool, Any]:
    """`clave` con puntos, como `pago_de.periodo`, entra en los subdocumentos."""
    valor: Any = documento
    for parte in clave.split("."):
        if not isinstance(valor, dict) or parte not in valor:
            return False, None
        valor = valor[parte]
    return True, valor


class Cursor:
    def __init__(self, filas: list[dict]):
        self._filas = filas

    def sort(self, campo, direccion=1):
        self._filas.sort(key=lambda d: d.get(campo), reverse=direccion == -1)
        return self

    def skip(self, n):
        self._filas = self._filas[n:]
        return self

    def limit(self, n):
        self._filas = self._filas[:n] if n else self._filas
        return self

    async def to_list(self, length=None):
        return copy.deepcopy(self._filas[:length] if length else self._filas)


class Resultado:
    def __init__(self, modificados=0, borrados=0):
        self.modified_count = modificados
        self.deleted_count = borrados
        self.upserted_id = None


class Coleccion:
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, filtro=None, _proyeccion=None):
        return Cursor([d for d in self.docs if _casa(d, filtro or {})])

    async def find_one(self, filtro, _proyeccion=None):
        filas = await self.find(filtro).to_list()
        return filas[0] if filas else None

    async def insert_one(self, documento):
        documento.setdefault("_id", ObjectId())
        self.docs.append(copy.deepcopy(documento))

    async def update_one(self, filtro, cambio, upsert=False):
        for documento in self.docs:
            if _casa(documento, filtro):
                documento.update(copy.deepcopy(cambio.get("$set", {})))
                return Resultado(modificados=1)
        if upsert:
            nuevo = {k: v for k, v in filtro.items() if not k.startswith("$")}
            nuevo.update(copy.deepcopy(cambio.get("$setOnInsert", {})))
            nuevo.update(copy.deepcopy(cambio.get("$set", {})))
            await self.insert_one(nuevo)
        return Resultado()

    async def update_many(self, filtro, cambio):
        filas = [d for d in self.docs if _casa(d, filtro)]
        for documento in filas:
            documento.update(copy.deepcopy(cambio["$set"]))
        return Resultado(modificados=len(filas))

    async def delete_many(self, filtro):
        filas = [d for d in self.docs if _casa(d, filtro)]
        for documento in filas:
            self.docs.remove(documento)
        return Resultado(borrados=len(filas))

    async def delete_one(self, filtro):
        for documento in self.docs:
            if _casa(documento, filtro):
                self.docs.remove(documento)
                return Resultado(borrados=1)
        return Resultado()

    async def count_documents(self, filtro):
        return sum(1 for d in self.docs if _casa(d, filtro))

    async def distinct(self, campo, filtro):
        return list({d.get(campo) for d in self.docs if _casa(d, filtro)})


class Base(dict):
    def __missing__(self, nombre):
        self[nombre] = Coleccion()
        return self[nombre]

    @property
    def externos(self) -> Coleccion:
        return self[NOMBRE_COL_COMPROBANTES_EXTERNOS]

    @property
    def comprobantes(self) -> Coleccion:
        return self[NOMBRE_COL_COMPROBANTES]


def correr(corutina):
    return asyncio.run(corutina)


@pytest.fixture
def db() -> Base:
    return Base()


# --- Datos -----------------------------------------------------------------------


def _externo(**cambios) -> dict:
    documento = {
        "_id": ObjectId(),
        "empresa_id": EMPRESA_ID,
        "id_externo": str(ObjectId()),
        "libro": "compras",
        "fuente": "factura",
        "tipo_evidencia": "comprobante",
        "tipo_cp": "01",
        "serie": "F001",
        "numero": "00000123",
        "nro_operacion": None,
        "fecha_operacion": datetime(2026, 9, 28, tzinfo=UTC),
        "moneda": "PEN",
        "total": Decimal128("118.00"),
        "base_imponible": Decimal128("100.00"),
        "igv": Decimal128("18.00"),
        "contraparte": {
            "tipo_doc_identidad": "6", "documento": "20100070970", "nombre": "Proveedor"
        },
        "descripcion": "Útiles de oficina",
        "confianza": 0.9,
        "campos_dudosos": [],
        "imagen": {"archivo": None},
        "periodo": PERIODO,
        "estado": "recibido",
        "creado_en": datetime.now(UTC),
        "comprobante_id": None,
    }
    documento.update(cambios)
    return documento


def _yape(**cambios) -> dict:
    return _externo(**{
        "libro": "ventas", "fuente": "yape", "tipo_evidencia": "voucher", "tipo_cp": "00",
        "serie": "", "numero": "", "nro_operacion": "0012345678",
        "total": Decimal128("150.00"), "base_imponible": None, "igv": None,
        "descripcion": "Pago recibido por Yape", **cambios,
    })


def _guardar_externo(db: Base, documento: dict) -> dict:
    correr(db.externos.insert_one(documento))
    return documento


def _crear_periodo(db: Base, periodo: str = PERIODO) -> None:
    correr(db[NOMBRE_COL_PERIODOS].insert_one({"empresa_id": EMPRESA_ID, "periodo": periodo}))


def _fila_sire(db: Base, **cambios) -> dict:
    fila = {
        "_id": ObjectId(), "empresa_id": EMPRESA_ID, "periodo": PERIODO, "libro": "compras",
        "origen": "sire", "tipo_cp": "01", "serie": "F001", "numero": "123",
        "serie_numero": "F001-123",
    }
    fila.update(cambios)
    correr(db.comprobantes.insert_one(fila))
    return fila


def _externo_guardado(db: Base, documento: dict) -> dict:
    return next(d for d in db.externos.docs if d["_id"] == documento["_id"])


# --- Mapeo -----------------------------------------------------------------------


def test_la_factura_entra_con_el_numero_normalizado_como_sunat():
    comprobante = integracion_externos.a_comprobante(_externo())

    assert comprobante.origen is Origen.EXTERNO
    # Los ceros de relleno del número se van, como en la propuesta SUNAT.
    assert (comprobante.tipo_cp, comprobante.serie, comprobante.numero) == ("01", "F001", "123")
    assert comprobante.fecha_emision.isoformat() == "2026-09-28"
    assert comprobante.documento_contraparte == "20100070970"
    assert comprobante.razon_social == "PROVEEDOR"
    assert (comprobante.base_imponible, comprobante.igv) == (Decimal("100.00"), Decimal("18.00"))
    # El Registro de Compras sale por destino: con IGV se asume gravado.
    assert (comprobante.base_imponible_dg, comprobante.igv_dg) == (
        Decimal("100.00"), Decimal("18.00")
    )
    assert comprobante.total == Decimal("118.00")


# --- Integración -----------------------------------------------------------------


def test_sin_periodo_se_queda_en_externos(db):
    externo = _guardar_externo(db, _externo())

    estado = correr(integracion_externos.integrar_uno(db, EMPRESA_ID, externo))

    assert estado == "recibido"
    assert db.comprobantes.docs == []
    assert _externo_guardado(db, externo)["estado"] == "recibido"


def test_al_existir_el_periodo_entra_como_fila_externa(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)

    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert conteo == {"integrados": 1, "ya_existian": 0, "vouchers": 0}
    [fila] = db.comprobantes.docs
    assert fila["origen"] == "externo"
    assert fila["serie_numero"] == "F001-123"
    assert fila["glosa"] == "Útiles de oficina"
    assert fila["estado_procesamiento"] == "sire_recibido"
    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "integrado"
    assert guardado["comprobante_id"] == str(fila["_id"])
    assert guardado["integrado_en"] is not None


def test_si_el_periodo_ya_lo_tenia_no_hace_nada(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)
    sire = _fila_sire(db)

    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID, PERIODO))

    assert conteo == {"integrados": 0, "ya_existian": 1, "vouchers": 0}
    assert db.comprobantes.docs == [sire]
    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "ya_existia"
    assert guardado["comprobante_id"] == str(sire["_id"])


def test_el_mismo_numero_en_el_otro_libro_no_cuenta_como_existente(db):
    _guardar_externo(db, _externo())
    _crear_periodo(db)
    _fila_sire(db, libro="ventas")

    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert conteo["integrados"] == 1


def test_el_voucher_no_se_copia_como_fila_del_periodo(db):
    yape = _guardar_externo(db, _yape())
    _crear_periodo(db)

    estado = correr(integracion_externos.integrar_uno(db, EMPRESA_ID, yape))

    assert estado == "integrado"
    assert db.comprobantes.docs == []
    guardado = _externo_guardado(db, yape)
    assert guardado["estado"] == "integrado"
    assert guardado["comprobante_id"] is None


def test_integrar_dos_veces_deja_una_sola_fila(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    # Otro refresco que leyó el externo antes de que se marcara.
    correr(integracion_externos._integrar(db, EMPRESA_ID, externo))

    assert len(db.comprobantes.docs) == 1


def test_solo_integra_los_de_periodos_que_existen(db):
    septiembre = _guardar_externo(db, _externo())
    octubre = _guardar_externo(
        db,
        _externo(numero="124", periodo="202610", fecha_operacion=datetime(2026, 10, 2, tzinfo=UTC)),
    )
    _crear_periodo(db)

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, septiembre)["estado"] == "integrado"
    assert _externo_guardado(db, octubre)["estado"] == "recibido"


def test_el_listado_de_externos_integra_los_pendientes(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)

    lista = correr(
        comprobantes_externos_service.listar(
            db, {"_id": EMPRESA_ID, "ruc": "20603391692"},
            libro=None, periodo=None, fuente=None, skip=0, limit=100,
        )
    )

    [item] = lista["items"]
    assert item["id"] == str(externo["_id"])
    assert item["estado"] == "integrado"
    assert item["serie_numero_periodo"] == "F001-123"
    assert item["comprobante_id"] == str(db.comprobantes.docs[0]["_id"])


# --- Propuesta SUNAT ---------------------------------------------------------------


def test_la_propuesta_sunat_reemplaza_a_la_fila_externa(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    fila_externa = db.comprobantes.docs[0]
    fila_externa["clasificacion_contable"] = {"cuenta_base": {"codigo": "6011"}}
    sire = _fila_sire(db)

    reemplazados = correr(
        integracion_externos.reconciliar_con_sunat(db, EMPRESA_ID, PERIODO, Libro.COMPRAS)
    )

    assert reemplazados == 1
    [queda] = db.comprobantes.docs
    assert queda["_id"] == sire["_id"]
    # Lo trabajado sobre la fila externa pasa a la de SUNAT...
    assert queda["clasificacion_contable"] == {"cuenta_base": {"codigo": "6011"}}
    # ...pero no la glosa que sólo era la descripción del bot: manda el detalle SUNAT.
    assert "glosa" not in queda
    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "ya_existia"
    assert guardado["comprobante_id"] == str(sire["_id"])


def test_la_glosa_editada_pasa_a_la_fila_sunat(db):
    _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    db.comprobantes.docs[0]["glosa"] = "Compra de papel bond"
    _fila_sire(db)

    correr(integracion_externos.reconciliar_con_sunat(db, EMPRESA_ID, PERIODO, Libro.COMPRAS))

    assert db.comprobantes.docs[0]["glosa"] == "Compra de papel bond"


def test_sin_gemela_sunat_la_fila_externa_se_queda(db):
    _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    _fila_sire(db, numero="999", serie_numero="F001-999")

    reemplazados = correr(
        integracion_externos.reconciliar_con_sunat(db, EMPRESA_ID, PERIODO, Libro.COMPRAS)
    )

    assert reemplazados == 0
    assert {f["origen"] for f in db.comprobantes.docs} == {"externo", "sire"}


# --- Borrar el periodo -------------------------------------------------------------------


def test_al_borrar_el_periodo_el_externo_vuelve_a_esperar(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    correr(repo_externos.devolver_a_pendiente(db, EMPRESA_ID, PERIODO))

    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "recibido"
    assert guardado["comprobante_id"] is None


def test_periodos_existentes(db):
    _crear_periodo(db)
    assert correr(repo_periodos.existentes(db, EMPRESA_ID, [PERIODO, "202610"])) == {PERIODO}
    assert correr(repo_periodos.existentes(db, EMPRESA_ID, [])) == set()


def test_desde_documento_acepta_el_origen_externo():
    comprobante = repo_comprobantes.desde_documento({"origen": "externo", "libro": "ventas"})
    assert comprobante.origen is Origen.EXTERNO


def test_el_cuadre_con_sunat_no_cuenta_las_filas_externas():
    from app.api.v1.routes.comprobantes import _solo_sunat

    datos = [{"origen": "sire"}, {"origen": "externo"}, {"origen": "sire"}]
    assert _solo_sunat(datos) == [{"origen": "sire"}, {"origen": "sire"}]


def test_si_la_integracion_falla_el_listado_sigue(db, monkeypatch):
    async def falla(*_args, **_kwargs):
        raise RuntimeError("mongo caído")

    monkeypatch.setattr(integracion_externos, "integrar_pendientes", falla)

    assert correr(integracion_externos.refrescar(db, EMPRESA_ID)) is None


# --- Vouchers como pagos -------------------------------------------------------------


def _boleta(db: Base, **cambios) -> dict:
    """Una boleta de ventas del periodo, de 150 soles, como la que paga el Yape."""
    return _fila_sire(db, **{
        "libro": "ventas", "tipo_cp": "03", "serie": "B001", "numero": "45",
        "serie_numero": "B001-45", "moneda": "PEN", "total": Decimal128("150.00"),
        "documento_contraparte": "45678912", "razon_social": "JUAN PEREZ", **cambios,
    })


def _yape_de_juan(**cambios) -> dict:
    return _yape(**{
        "contraparte": {"tipo_doc_identidad": "1", "documento": "45678912", "nombre": "JUAN PEREZ"},
        **cambios,
    })


def test_voucher_sin_periodo_espera(db):
    yape = _guardar_externo(db, _yape_de_juan())

    assert correr(integracion_externos.integrar_uno(db, EMPRESA_ID, yape)) == "recibido"
    assert _externo_guardado(db, yape).get("pago_de") is None


def test_con_una_sola_candidata_el_voucher_queda_como_su_pago(db):
    _crear_periodo(db)
    boleta = _boleta(db)
    yape = _guardar_externo(db, _yape_de_juan())

    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert conteo["vouchers"] == 1
    guardado = _externo_guardado(db, yape)
    assert guardado["estado"] == "integrado"
    assert guardado["pago_de"] == {
        "periodo": PERIODO, "libro": "ventas", "tipo_cp": "03", "serie": "B001", "numero": "45"
    }
    assert guardado["asociacion"] == "auto"
    # El voucher no es una fila del periodo.
    assert db.comprobantes.docs == [boleta]


def test_con_dos_candidatas_no_adivina(db):
    _crear_periodo(db)
    _boleta(db)
    _boleta(db, numero="46", serie_numero="B001-46")
    yape = _guardar_externo(db, _yape_de_juan())

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, yape).get("pago_de") is None


def test_otro_documento_de_contraparte_descarta_la_candidata(db):
    _crear_periodo(db)
    _boleta(db, documento_contraparte="10203040")
    yape = _guardar_externo(db, _yape_de_juan())

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, yape).get("pago_de") is None


def test_un_comprobante_ya_pagado_no_se_asocia_a_otro_voucher(db):
    _crear_periodo(db)
    _boleta(db)
    primero = _guardar_externo(db, _yape_de_juan())
    segundo = _guardar_externo(db, _yape_de_juan(nro_operacion="0099999999"))

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    asociados = [
        _externo_guardado(db, v).get("pago_de") is not None for v in (primero, segundo)
    ]
    assert asociados.count(True) == 1


def test_asociar_a_mano_y_desasociar(db):
    _crear_periodo(db)
    _boleta(db)
    _boleta(db, numero="46", serie_numero="B001-46")
    yape = _guardar_externo(db, _yape_de_juan())
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    pago = correr(
        pagos_vouchers.asociar_manual(db, EMPRESA_ID, PERIODO, str(yape["_id"]), "B001-46")
    )
    assert pago["serie_numero"] == "B001-46"
    assert _externo_guardado(db, yape)["pago_de"]["numero"] == "46"

    correr(pagos_vouchers.asociar_manual(db, EMPRESA_ID, PERIODO, str(yape["_id"]), None))
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID, PERIODO))
    guardado = _externo_guardado(db, yape)
    # Desasociado a mano: la asociación automática no lo vuelve a tocar.
    assert guardado["pago_de"] is None
    assert guardado["asociacion"] == "manual"


def test_asociar_a_un_comprobante_que_no_existe(db):
    _crear_periodo(db)
    yape = _guardar_externo(db, _yape_de_juan())
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    with pytest.raises(pagos_vouchers.ComprobanteNoEncontrado):
        correr(
            pagos_vouchers.asociar_manual(db, EMPRESA_ID, PERIODO, str(yape["_id"]), "B009-1")
        )


def test_el_comprobante_trae_su_pago_y_aparte_los_vouchers_sin_comprobante(db):
    _crear_periodo(db)
    _boleta(db)
    _guardar_externo(db, _yape_de_juan())
    _guardar_externo(db, _yape_de_juan(
        fuente="plin", nro_operacion="5566", total=Decimal128("80.00"),
    ))
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    # Serializado, como lo pasa la ruta: sin periodo.
    datos = [{"libro": "ventas", "tipo_cp": "03", "serie": "B001", "numero": "45"}]
    sin_comprobante = correr(pagos_vouchers.adjuntar_pagos(db, EMPRESA_ID, PERIODO, datos))

    [pago] = datos[0]["pagos"]
    assert (pago["medio_pago"], pago["codigo_medio_pago"], pago["nro_operacion"]) == (
        "Yape", "003", "0012345678"
    )
    assert pago["serie_numero"] == "B001-45"
    [suelto] = sin_comprobante
    assert (suelto["medio_pago"], suelto["nro_operacion"], suelto["total"]) == (
        "Plin", "5566", "80.00"
    )


def test_el_pago_sigue_cuando_la_fila_sunat_reemplaza_a_la_externa(db):
    _crear_periodo(db)
    boleta_bot = _guardar_externo(db, _externo(
        libro="ventas", fuente="boleta", tipo_cp="03", serie="B001", numero="45",
        total=Decimal128("150.00"), base_imponible=None, igv=None,
        contraparte={"tipo_doc_identidad": "1", "documento": "45678912", "nombre": "JUAN PEREZ"},
    ))
    _guardar_externo(db, _yape_de_juan())
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    assert _externo_guardado(db, boleta_bot)["estado"] == "integrado"

    _boleta(db)
    correr(integracion_externos.reconciliar_con_sunat(db, EMPRESA_ID, PERIODO, Libro.VENTAS))

    [fila] = db.comprobantes.docs
    assert fila["origen"] == "sire"
    datos = [dict(fila)]
    correr(pagos_vouchers.adjuntar_pagos(db, EMPRESA_ID, PERIODO, datos))
    assert [p["medio_pago"] for p in datos[0]["pagos"]] == ["Yape"]


def test_la_fila_de_voucher_de_la_version_anterior_se_retira(db):
    _crear_periodo(db)
    vieja = {
        "_id": ObjectId(), "empresa_id": EMPRESA_ID, "periodo": PERIODO, "libro": "ventas",
        "origen": "externo", "tipo_cp": "00", "serie": "NIUBIZ", "numero": "38439",
        "serie_numero": "NIUBIZ-38439",
    }
    correr(db.comprobantes.insert_one(vieja))
    sire = _boleta(db)
    niubiz = _guardar_externo(db, _yape_de_juan(
        fuente="niubiz", nro_operacion="38439", estado="integrado",
        comprobante_id=str(vieja["_id"]),
    ))

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID, PERIODO))

    assert db.comprobantes.docs == [sire]
    guardado = _externo_guardado(db, niubiz)
    assert guardado["comprobante_id"] is None
    assert guardado["pago_de"]["serie"] == "B001"


def test_externos_muestra_el_comprobante_que_paga_el_voucher():
    documento = _yape_de_juan(
        estado="integrado",
        pago_de={"libro": "ventas", "tipo_cp": "03", "serie": "B001", "numero": "45"},
    )
    respuesta = comprobantes_externos_service.a_respuesta(documento, "20603391692")
    assert respuesta["serie_numero_periodo"] == "B001-45"

    sin_pago = comprobantes_externos_service.a_respuesta(
        _yape_de_juan(estado="integrado"), "20603391692"
    )
    assert sin_pago["serie_numero_periodo"] is None


# --- Vouchers que pagan un comprobante del periodo anterior ------------------------


def _yape_de_octubre(**cambios) -> dict:
    return _yape_de_juan(
        periodo="202610", fecha_operacion=datetime(2026, 10, 2, tzinfo=UTC), **cambios
    )


def test_un_voucher_de_octubre_paga_la_boleta_de_septiembre(db):
    _crear_periodo(db)
    _crear_periodo(db, "202610")
    _boleta(db)
    yape = _guardar_externo(db, _yape_de_octubre())

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, yape)["pago_de"]["periodo"] == PERIODO
    # El pago se ve en la boleta, en septiembre...
    datos = [{"libro": "ventas", "tipo_cp": "03", "serie": "B001", "numero": "45"}]
    correr(pagos_vouchers.adjuntar_pagos(db, EMPRESA_ID, PERIODO, datos))
    [pago] = datos[0]["pagos"]
    assert (pago["periodo"], pago["periodo_comprobante"]) == ("202610", PERIODO)
    # ...y octubre no lo trae como suelto.
    assert correr(pagos_vouchers.adjuntar_pagos(db, EMPRESA_ID, "202610", [])) == []


def test_una_candidata_en_cada_mes_es_ambigua(db):
    _crear_periodo(db)
    _crear_periodo(db, "202610")
    _boleta(db)
    _boleta(db, periodo="202610", numero="60", serie_numero="B001-60")
    yape = _guardar_externo(db, _yape_de_octubre())

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, yape).get("pago_de") is None
    [voucher] = correr(pagos_vouchers.vouchers_con_candidatas(db, EMPRESA_ID, "202610"))
    assert {(c["periodo"], c["serie_numero"]) for c in voucher["candidatas"]} == {
        (PERIODO, "B001-45"), ("202610", "B001-60")
    }


def test_un_voucher_no_paga_un_comprobante_del_mes_siguiente(db):
    _crear_periodo(db)
    _crear_periodo(db, "202610")
    _boleta(db, periodo="202610")
    yape = _guardar_externo(db, _yape_de_juan())

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, yape).get("pago_de") is None


def test_la_boleta_de_septiembre_ya_pagada_en_septiembre_no_la_toma_octubre(db):
    _crear_periodo(db)
    _crear_periodo(db, "202610")
    _boleta(db)
    septiembre = _guardar_externo(db, _yape_de_juan())
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID, PERIODO))
    octubre = _guardar_externo(db, _yape_de_octubre(nro_operacion="0099999999"))

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, septiembre)["pago_de"]["periodo"] == PERIODO
    assert _externo_guardado(db, octubre).get("pago_de") is None


def test_sincronizar_septiembre_asocia_los_vouchers_de_octubre(db):
    _crear_periodo(db)
    _crear_periodo(db, "202610")
    yape = _guardar_externo(db, _yape_de_octubre())
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    assert _externo_guardado(db, yape).get("pago_de") is None

    _boleta(db)  # llega con la propuesta de septiembre
    correr(pagos_vouchers.asociar_alrededor(db, EMPRESA_ID, PERIODO))

    assert _externo_guardado(db, yape)["pago_de"]["serie"] == "B001"


def test_a_mano_desde_octubre_a_una_boleta_de_septiembre_y_desasociar_desde_ella(db):
    _crear_periodo(db)
    _crear_periodo(db, "202610")
    _boleta(db, total=Decimal128("999.00"))
    yape = _guardar_externo(db, _yape_de_octubre())
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    pago = correr(pagos_vouchers.asociar_manual(
        db, EMPRESA_ID, "202610", str(yape["_id"]), "B001-45"
    ))
    assert (pago["serie_numero"], pago["periodo_comprobante"]) == ("B001-45", PERIODO)

    # Desde la ficha de la boleta, en septiembre.
    correr(pagos_vouchers.asociar_manual(db, EMPRESA_ID, PERIODO, str(yape["_id"]), None))
    assert _externo_guardado(db, yape)["pago_de"] is None


def test_a_mano_no_llega_a_dos_meses_atras(db):
    _crear_periodo(db, "202610")
    _boleta(db, periodo="202608")
    yape = _guardar_externo(db, _yape_de_octubre())
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    with pytest.raises(pagos_vouchers.ComprobanteNoEncontrado):
        correr(pagos_vouchers.asociar_manual(
            db, EMPRESA_ID, "202610", str(yape["_id"]), "B001-45", "202608"
        ))


def test_externos_enlaza_al_periodo_del_comprobante_que_paga():
    documento = _yape_de_octubre(
        estado="integrado",
        pago_de={
            "periodo": PERIODO, "libro": "ventas", "tipo_cp": "03", "serie": "B001",
            "numero": "45",
        },
    )
    respuesta = comprobantes_externos_service.a_respuesta(documento, "20603391692")
    assert (respuesta["serie_numero_periodo"], respuesta["periodo_comprobante"]) == (
        "B001-45", PERIODO
    )


def test_periodo_anterior_y_siguiente():
    from app.domain import periodo

    assert periodo.anterior("202601") == "202512"
    assert periodo.siguiente("202612") == "202701"
    assert periodo.anterior("202610") == "202609"
