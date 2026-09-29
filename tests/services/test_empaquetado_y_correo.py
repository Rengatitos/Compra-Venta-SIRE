"""Archivos finales en el ZIP y correo de fin de solicitud."""

from __future__ import annotations

import asyncio
import io
import smtplib
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from app.domain.comprobante import Libro
from app.domain.configuracion_correo import ConfiguracionCorreo
from app.domain.jobs import Job, TipoJob
from app.services import correo_service, empaquetado_service
from app.services.cola.errores import ErrorPermanente, ErrorTransitorio
from app.services.plantilla_excel import ErrorTipoCambio, excel_plantilla

RUC_A = "20610202251"
RUC_B = "20603391692"
EMPRESAS = {
    RUC_A: {
        "_id": ObjectId(), "ruc": RUC_A, "nombre": "Alfa", "correos_notificacion": ["c@alfa.pe"],
    },
    RUC_B: {"_id": ObjectId(), "ruc": RUC_B, "nombre": "Beta", "correos_notificacion": []},
}
SIRE = datetime(2026, 9, 27, 15, tzinfo=UTC)


def item(ruc=RUC_A, periodo="202608", estado="completado", observaciones=None):
    return {
        "ruc": ruc, "nombre": EMPRESAS[ruc]["nombre"], "periodo": periodo, "estado": estado,
        "observaciones": observaciones or [], "pasos": [],
    }


@pytest.fixture
def datos(monkeypatch, tmp_path):
    monkeypatch.setattr(empaquetado_service.almacen_pdf.settings, "SUNAT_DATA_DIR", str(tmp_path))
    pdf = tmp_path / RUC_A / "compras" / "2026" / "08" / "facturas" / "F001-1.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF compra")
    venta = tmp_path / RUC_A / "ventas" / "2026" / "08" / "boletas" / "B001-7.pdf"
    venta.parent.mkdir(parents=True)
    venta.write_bytes(b"%PDF venta")

    comprobantes = {
        Libro.COMPRAS: [
            {"serie_numero": "F001-1", "tipo_cp": "01", "documento_contraparte": "20100070970",
             "pdf_sunat": {"ruta": f"{RUC_A}/compras/2026/08/facturas/F001-1.pdf"}},
            {"serie_numero": "F001-2", "tipo_cp": "01", "documento_contraparte": "20100070970"},
        ],
        Libro.VENTAS: [
            {"serie_numero": "B001-7", "tipo_cp": "03",
             "pdf_sunat": {"ruta": f"{RUC_A}/ventas/2026/08/boletas/B001-7.pdf"}},
        ],
    }

    async def listar(db, empresa_id, periodo, libro=None, limit=0):
        return comprobantes[libro] if empresa_id == str(EMPRESAS[RUC_A]["_id"]) else []

    async def por_ruc(db, ruc):
        return EMPRESAS.get(ruc)

    monkeypatch.setattr(empaquetado_service.repo_comprobantes, "listar", listar)
    monkeypatch.setattr(empaquetado_service.repo_empresas, "obtener_por_ruc", por_ruc)
    monkeypatch.setattr(
        empaquetado_service.repo_jobs, "ultima_sincronizacion_sire", AsyncMock(return_value=SIRE)
    )
    monkeypatch.setattr(
        empaquetado_service.destino_compras, "detectar", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        empaquetado_service, "excel_plantilla", lambda datos, libro, destino: io.BytesIO(b"xlsx")
    )
    monkeypatch.setattr(correo_service.repo_empresas, "obtener_por_ruc", por_ruc)
    return tmp_path


def nombres_en(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return set(zf.namelist())


def test_el_zip_organiza_cada_empresa_y_periodo_en_su_carpeta(datos):
    destino = datos / "solicitudes" / "s1" / "DESCARGA_2026-09-27.zip"

    resumen = asyncio.run(empaquetado_service.armar_zip(None, [item()], destino))

    carpeta = "20610202251_2026-08_2026-09-27"
    nombres = nombres_en(destino)
    assert f"{carpeta}/Ventas/Reporte_Ventas.xlsx" in nombres
    assert f"{carpeta}/Compras/Reporte_Compras.xlsx" in nombres
    assert f"{carpeta}/Comprobantes/Facturas/COMPRA_20100070970_F001-1.pdf" in nombres
    assert f"{carpeta}/Comprobantes/Boletas/VENTA_20610202251_B001-7.pdf" in nombres
    assert f"{carpeta}/Comprobantes/Otros/" in nombres  # vacía, pero presente
    assert resumen["carpetas"][0]["pdfs"] == 2
    assert resumen["carpetas"][0]["sin_pdf"] == 1
    with zipfile.ZipFile(destino) as zf:
        assert "1 comprobantes sin PDF" in zf.read(f"{carpeta}/observaciones.txt").decode()
    assert not destino.with_suffix(".parcial").exists()


def test_sin_tipo_de_cambio_no_hay_excel_de_ese_libro_pero_si_el_motivo(datos, monkeypatch):
    def plantilla(datos_, libro, destino):
        if libro is Libro.COMPRAS:
            raise ErrorTipoCambio([{"serie_numero": "F001-1"}])
        return io.BytesIO(b"xlsx")

    monkeypatch.setattr(empaquetado_service, "excel_plantilla", plantilla)
    destino = datos / "z.zip"
    resumen = asyncio.run(empaquetado_service.armar_zip(None, [item()], destino))

    assert not any(n.endswith("Reporte_Compras.xlsx") for n in nombres_en(destino))
    assert any("tipo de cambio" in o for o in resumen["carpetas"][0]["observaciones"])


def test_un_periodo_sin_comprobantes_genera_el_excel_vacio_de_la_plantilla():
    # El empaquetado lo pide siempre, aunque SUNAT no tenga nada del periodo.
    assert excel_plantilla([], Libro.VENTAS).getvalue()[:2] == b"PK"


# --- Correo -----------------------------------------------------------------


def solicitud_con_zip(datos, items):
    sid = ObjectId()
    raiz = empaquetado_service.raiz_solicitud(str(sid))
    raiz.mkdir(parents=True)
    (raiz / "DESCARGA_2026-09-27.zip").write_bytes(b"PK" * 10)
    return {
        "_id": sid, "creado_por": "Contador@Example.com", "creado_en": SIRE, "items": items,
        "zip": {"archivo": "DESCARGA_2026-09-27.zip", "bytes": 20}, "envios": [],
    }


class RepoSolicitudes:
    def __init__(self, solicitud):
        self.solicitud = solicitud

    async def obtener(self, db, sid):
        return self.solicitud

    async def actualizar(self, db, sid, cambios):
        self.solicitud.update(cambios)

    async def guardar_envio(self, db, sid, indice, cambios):
        self.solicitud["envios"][indice].update(cambios)


@pytest.fixture
def smtp(monkeypatch):
    """SMTP falso y la configuración que se leería de Mongo."""
    estado = SimpleNamespace(
        enviados=[],
        config=ConfiguracionCorreo(
            host="smtp.example.com",
            usuario="sire@example.com",
            url_publica="https://sire.example.com",
        ),
    )

    async def obtener(db):
        return estado.config

    monkeypatch.setattr(correo_service.repo_configuracion, "obtener_correo", obtener)
    monkeypatch.setattr(correo_service.settings, "CORREO_SMTP_PASSWORD", "clave-app")
    monkeypatch.setattr(
        correo_service, "_enviar",
        lambda mensaje, config, timeout=60: estado.enviados.append(mensaje),
    )
    return estado


def enviar(monkeypatch, solicitud, intentos=1, max_intentos=5):
    repo = RepoSolicitudes(solicitud)
    for nombre in ("obtener", "actualizar", "guardar_envio"):
        monkeypatch.setattr(correo_service.repo_solicitudes, nombre, getattr(repo, nombre))
    job = Job(
        tipo=TipoJob.ENVIO_CORREO, ruc="", periodo="", solicitud_id=str(solicitud["_id"]),
        intentos=intentos, max_intentos=max_intentos,
    )
    return asyncio.run(correo_service.enviar_solicitud(None, job, AsyncMock()))


def test_solo_quien_pidio_la_solicitud_recibe_el_zip_completo(datos, smtp, monkeypatch):
    # Alfa tiene `correos_notificacion`, pero ya no se usan.
    solicitud = solicitud_con_zip(datos, [item(RUC_A), item(RUC_B)])

    resultado = enviar(monkeypatch, solicitud)

    assert resultado == {"enviados": 1, "bloqueados": 0, "fallidos": 0}
    [mensaje] = smtp.enviados
    assert mensaje["To"] == "contador@example.com"
    assert mensaje["From"] == "Sire Apaclla <sire@example.com>"
    assert next(mensaje.iter_attachments()).get_filename() == "DESCARGA_2026-09-27.zip"
    [envio] = solicitud["envios"]
    assert envio["rucs"] == sorted([RUC_A, RUC_B])
    assert envio["modo"] == "adjunto"


def test_fuera_de_la_lista_blanca_no_se_escribe(datos, smtp, monkeypatch):
    smtp.config = replace(smtp.config, destinatarios_permitidos=["espinozavaleracinve@gmail.com"])
    solicitud = solicitud_con_zip(datos, [item(RUC_A)])

    resultado = enviar(monkeypatch, solicitud)

    assert resultado["bloqueados"] == 1
    assert smtp.enviados == []


def test_un_zip_grande_va_como_enlace_firmado(datos, smtp, monkeypatch):
    smtp.config = replace(smtp.config, max_adjunto_mb=0, dias_enlace=3)
    solicitud = solicitud_con_zip(datos, [item(RUC_B)])

    enviar(monkeypatch, solicitud)

    [mensaje] = smtp.enviados
    assert list(mensaje.iter_attachments()) == []
    texto = mensaje.get_body(("plain",)).get_content()
    assert "https://sire.example.com/api/v1/descargas/" in texto
    assert "válido 3 días" in texto
    assert solicitud["envios"][0]["modo"] == "enlace"


def test_sin_smtp_configurado_falla_sin_reintentar(datos, smtp, monkeypatch):
    smtp.config = replace(smtp.config, host="")
    solicitud = solicitud_con_zip(datos, [item(RUC_B)])

    resultado = enviar(monkeypatch, solicitud)

    assert resultado["fallidos"] == 1
    assert "Correos" in solicitud["envios"][0]["error"]


def test_un_fallo_pasajero_reintenta_solo_lo_que_no_salio(datos, smtp, monkeypatch):
    llamadas = []

    def falla_una_vez(mensaje, config, timeout=60):
        llamadas.append(mensaje["To"])
        if len(llamadas) == 1:
            raise smtplib.SMTPServerDisconnected("se cortó")

    monkeypatch.setattr(correo_service, "_enviar", falla_una_vez)
    solicitud = solicitud_con_zip(datos, [item(RUC_B)])

    with pytest.raises(ErrorTransitorio):
        enviar(monkeypatch, solicitud, intentos=1)
    assert solicitud["envios"][0]["estado"] == "fallido"

    resultado = enviar(monkeypatch, solicitud, intentos=2)
    assert resultado["enviados"] == 1
    assert solicitud["envios"][0]["intentos"] == 2


def test_una_contrasena_smtp_mala_no_se_reintenta(datos, smtp, monkeypatch):
    def rechaza(mensaje, config, timeout=60):
        raise smtplib.SMTPAuthenticationError(535, b"bad")

    monkeypatch.setattr(correo_service, "_enviar", rechaza)
    solicitud = solicitud_con_zip(datos, [item(RUC_B)])

    resultado = enviar(monkeypatch, solicitud)  # no lanza: no hay nada que reintentar

    assert resultado["fallidos"] == 1
    assert "contraseña" in solicitud["envios"][0]["error"]


def test_el_correo_por_defecto_cuenta_las_etapas_y_el_estado_de_cada_periodo(datos):
    pasos = [
        {"paso": "sire_compras", "estado": "completado"},
        {"paso": "detalle_compras", "estado": "fallido"},
        {"paso": "clasificacion_compras", "estado": "omitido"},
    ]
    solicitud = solicitud_con_zip(datos, [{**item(RUC_A, estado="con_errores"), "pasos": pasos}])
    envio = {"correo": "a@b.pe", "rucs": [RUC_A], "empresas": [{"ruc": RUC_A, "nombre": "Alfa"}]}

    mensaje = correo_service.construir(
        solicitud, envio, ConfiguracionCorreo(), adjunto=None, enlace=None
    )

    texto = mensaje.get_body(("plain",)).get_content()
    assert "Descarga de reportes SIRE: completado" in texto
    assert "Descarga de comprobantes: con errores" in texto
    assert "clasificación con IA: omitido" in texto
    assert "Alfa (20610202251) · 08/2026: Completado con observaciones" in texto
    assert mensaje["Subject"] == "Sire · Procesamiento terminado: 1 empresa, 1 periodo"
    html = mensaje.get_body(("html",)).get_content()
    assert "<table" in html and "<li>Descarga de comprobantes" in html


def test_la_plantilla_guardada_manda_sobre_el_texto(datos):
    config = ConfiguracionCorreo(
        plantilla_asunto="Listo {{empresas}}\npara revisar",
        plantilla_cuerpo="Hola {{destinatario}}:\n<b>{{periodos}}</b> {{desconocida}}",
    )
    solicitud = solicitud_con_zip(datos, [item(RUC_A)])
    envio = {"correo": "a@b.pe", "rucs": [RUC_A], "empresas": [{"ruc": RUC_A, "nombre": "Alfa"}]}

    mensaje = correo_service.construir(solicitud, envio, config, adjunto=None, enlace=None)

    # El salto de línea del asunto no rompe la cabecera.
    assert mensaje["Subject"] == "Listo Alfa para revisar"
    assert mensaje.get_body(("plain",)).get_content().startswith("Hola a@b.pe:\n<b>08/2026</b>")
    html = mensaje.get_body(("html",)).get_content()
    # El texto de la plantilla se escapa y la variable desconocida queda a la vista.
    assert "&lt;b&gt;08/2026&lt;/b&gt;" in html
    assert "{{desconocida}}" in html


class SmtpFalso:
    creados: list = []

    def __init__(self, host, puerto, timeout):
        self.acciones = [("conectar", host, puerto, timeout)]
        SmtpFalso.creados.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.acciones.append(("starttls",))

    def login(self, usuario, password):
        self.acciones.append(("login", usuario, password))

    def send_message(self, mensaje):
        self.acciones.append(("enviar", mensaje["To"]))


class SmtpSslFalso(SmtpFalso):
    pass


@pytest.mark.parametrize(
    ("seguridad", "clase", "con_starttls"),
    [("starttls", SmtpFalso, True), ("ssl", SmtpSslFalso, False), ("ninguna", SmtpFalso, False)],
)
def test_la_seguridad_elige_la_conexion(monkeypatch, seguridad, clase, con_starttls):
    from email.message import EmailMessage

    from app.core.encryption import encrypt_password

    SmtpFalso.creados = []
    monkeypatch.setattr(correo_service.smtplib, "SMTP", SmtpFalso)
    monkeypatch.setattr(correo_service.smtplib, "SMTP_SSL", SmtpSslFalso)
    config = ConfiguracionCorreo(
        host="smtp.example.com", puerto=465, seguridad=seguridad, usuario="u@x.pe",
        password_cifrada=encrypt_password("clave-app"),
    )
    mensaje = EmailMessage()
    mensaje["To"] = "a@b.pe"

    correo_service._enviar(mensaje, config)

    [conexion] = SmtpFalso.creados
    assert type(conexion) is clase
    assert (("starttls",) in conexion.acciones) is con_starttls
    assert ("login", "u@x.pe", "clave-app") in conexion.acciones


def test_la_prueba_respeta_la_lista_blanca_y_exige_servidor(smtp):
    smtp.config = replace(smtp.config, destinatarios_permitidos=["ok@x.pe"])
    with pytest.raises(correo_service.CorreoNoEnviado, match="permitidos"):
        asyncio.run(correo_service.enviar_prueba(None, "otro@x.pe"))

    asyncio.run(correo_service.enviar_prueba(None, "ok@x.pe"))
    assert smtp.enviados[0]["Subject"].startswith("[Prueba] Sire")

    smtp.config = replace(smtp.config, host="")
    with pytest.raises(correo_service.CorreoNoEnviado, match="Correos"):
        asyncio.run(correo_service.enviar_prueba(None, "ok@x.pe"))


def test_sin_contrasena_de_aplicacion_no_se_intenta_enviar(datos, smtp, monkeypatch):
    monkeypatch.setattr(correo_service.settings, "CORREO_SMTP_PASSWORD", None)
    solicitud = solicitud_con_zip(datos, [item(RUC_B)])

    resultado = enviar(monkeypatch, solicitud)

    assert resultado["fallidos"] == 1
    assert smtp.enviados == []
    assert "contraseña de aplicación" in solicitud["envios"][0]["error"]


def test_una_solicitud_borrada_es_un_error_permanente(monkeypatch):
    monkeypatch.setattr(correo_service.repo_solicitudes, "obtener", AsyncMock(return_value=None))
    job = Job(tipo=TipoJob.ENVIO_CORREO, ruc="", periodo="", solicitud_id="x")
    with pytest.raises(ErrorPermanente):
        asyncio.run(correo_service.enviar_solicitud(None, job, AsyncMock()))
