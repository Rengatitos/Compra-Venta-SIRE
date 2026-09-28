from datetime import UTC, datetime

from app.domain.solicitudes import (
    EstadoEnvio,
    EstadoItem,
    EstadoPaso,
    EstadoSolicitud,
    Paso,
    estado_final_item,
    estado_final_solicitud,
    nombre_carpeta,
    nombre_zip,
    omitir_restantes,
    pasos_del_item,
    siguiente_paso,
)


def nombres(pasos):
    return [p["paso"] for p in pasos]


def test_los_pasos_van_en_orden_y_las_credenciales_solo_si_faltan():
    con = pasos_del_item(necesita_credenciales=True, clasificar=True, motivo_sin_clasificar=None)
    sin = pasos_del_item(necesita_credenciales=False, clasificar=True, motivo_sin_clasificar=None)
    assert nombres(con) == [p.value for p in Paso]
    assert nombres(sin) == [p.value for p in Paso if p is not Paso.CREDENCIALES]
    assert all(p["estado"] == "pendiente" for p in con)


def test_sin_clasificar_la_clasificacion_queda_omitida_con_su_motivo():
    pasos = pasos_del_item(
        necesita_credenciales=False, clasificar=False, motivo_sin_clasificar="Deshabilitado"
    )
    omitidos = [p for p in pasos if p["estado"] == "omitido"]
    assert nombres(omitidos) == ["clasificacion_compras", "clasificacion_ventas"]
    assert {p["nota"] for p in omitidos} == {"Deshabilitado"}


def test_siguiente_paso_salta_los_cerrados():
    pasos = pasos_del_item(necesita_credenciales=False, clasificar=True, motivo_sin_clasificar=None)
    pasos[0]["estado"] = EstadoPaso.COMPLETADO.value
    assert siguiente_paso(pasos) == 1
    for p in pasos:
        p["estado"] = EstadoPaso.COMPLETADO.value
    assert siguiente_paso(pasos) is None


def test_sin_sire_el_item_falla_y_con_otro_fallo_queda_con_errores():
    pasos = pasos_del_item(necesita_credenciales=False, clasificar=True, motivo_sin_clasificar=None)
    pasos[0]["estado"] = EstadoPaso.FALLIDO.value
    omitir_restantes(pasos, "sin SIRE")
    assert estado_final_item(pasos) is EstadoItem.FALLIDO
    assert siguiente_paso(pasos) is None

    otros = pasos_del_item(necesita_credenciales=False, clasificar=True, motivo_sin_clasificar=None)
    for p in otros:
        p["estado"] = EstadoPaso.COMPLETADO.value
    otros[-1]["estado"] = EstadoPaso.FALLIDO.value
    assert estado_final_item(otros) is EstadoItem.CON_ERRORES


def test_estado_final_de_la_solicitud():
    ok = [EstadoItem.COMPLETADO]
    assert estado_final_solicitud(ok, [EstadoEnvio.ENVIADO]) is EstadoSolicitud.COMPLETADA
    # Un destinatario bloqueado por el entorno no es un error.
    assert estado_final_solicitud(ok, [EstadoEnvio.BLOQUEADO]) is EstadoSolicitud.COMPLETADA
    assert (
        estado_final_solicitud(ok, [EstadoEnvio.FALLIDO])
        is EstadoSolicitud.COMPLETADA_CON_ERRORES
    )
    assert (
        estado_final_solicitud([EstadoItem.COMPLETADO, EstadoItem.CON_ERRORES], [])
        is EstadoSolicitud.COMPLETADA_CON_ERRORES
    )
    assert estado_final_solicitud([EstadoItem.FALLIDO], []) is EstadoSolicitud.FALLIDA


def test_la_carpeta_lleva_ruc_periodo_y_el_dia_en_lima_de_la_ultima_descarga():
    # 03:00 UTC del 28 son las 22:00 del 27 en Lima.
    ultima = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)
    assert nombre_carpeta("20123456789", "202609", ultima) == "20123456789_2026-09_2026-09-27"


def test_el_zip_se_nombra_por_el_dia_de_la_solicitud():
    assert nombre_zip(datetime(2026, 9, 27, 15, tzinfo=UTC)) == "DESCARGA_2026-09-27.zip"
