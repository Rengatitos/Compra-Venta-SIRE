import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.sunat import ticket_rce
from app.services.sunat.auth import ErrorSunat


class Respuesta:
    def __init__(self, datos=None, contenido=b""):
        self._datos = datos
        self.content = contenido

    def json(self):
        return self._datos


def test_ciclo_ticket_genera_espera_y_descarga(monkeypatch):
    respuestas = [
        Respuesta({"numTicket": "20260300000043"}),
        Respuesta({"registros": [{"numTicket": "20260300000043"}]}),
        Respuesta(
            {
                "registros": [
                    {
                        "showReporteDescarga": "1",
                        "numTicket": "20260300000043",
                        "codProceso": "10",
                        "codEstadoProceso": "06",
                        "desEstadoProceso": "Terminado",
                        "perTributario": "202608",
                        "archivoReporte": [
                            {
                                "nomArchivoReporte": "propuesta.zip",
                                "codTipoAchivoReporte": "00",
                            }
                        ],
                    }
                ]
            }
        ),
        Respuesta(contenido=b"PK-archivo"),
    ]
    peticion = AsyncMock(side_effect=respuestas)
    monkeypatch.setattr(ticket_rce, "_peticion", peticion)
    monkeypatch.setattr(ticket_rce.asyncio, "sleep", AsyncMock())

    numero, contenido = asyncio.run(
        ticket_rce.obtener_zip(
            object(), {"ruc": "20123456789"}, "202608", intentos=3
        )
    )
    assert numero == "20260300000043"
    assert contenido == b"PK-archivo"
    assert peticion.await_count == 4


def test_consulta_ignora_estado_transitorio(monkeypatch):
    peticion = AsyncMock(
        return_value=Respuesta(
            {
                "registros": [
                    {
                        "numTicket": "T1",
                        "codEstadoProceso": "02",
                        "desEstadoProceso": "En proceso",
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(ticket_rce, "_peticion", peticion)

    resultado = asyncio.run(ticket_rce.consultar(object(), {}, "202608", "T1"))

    assert resultado is None


def test_configura_origen_del_portal_y_acepta_typo_sunat():
    assert ticket_rce.COD_ORIGEN_PROPUESTA == "1"
    archivo = ticket_rce._buscar_archivo(
        {
            "codProceso": "10",
            "perTributario": "202608",
            "archivoReporte": [
                {
                    "nomArchivoReporte": "propuesta.zip",
                    "codTipoAchivoReporte": "00",
                }
            ],
        }
    )
    assert archivo == {
        "nomArchivoReporte": "propuesta.zip",
        "codTipoArchivoReporte": "00",
        "codProceso": "10",
        "perTributario": "202608",
    }


def test_ticket_que_no_termina_falla_visiblemente(monkeypatch):
    monkeypatch.setattr(ticket_rce, "generar", AsyncMock(return_value="T1"))
    monkeypatch.setattr(ticket_rce, "consultar", AsyncMock(return_value=None))
    monkeypatch.setattr(ticket_rce.asyncio, "sleep", AsyncMock())
    with pytest.raises(ErrorSunat, match="no terminó"):
        asyncio.run(ticket_rce.obtener_zip(object(), {}, "202608", intentos=2))
