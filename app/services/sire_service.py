import asyncio
import json
import logging
from datetime import datetime, timedelta

import requests

from app.core.config import settings
from app.core.encryption import decrypt_password


logger = logging.getLogger(__name__)


async def obtener_token_api_oficial(ruc, usuario, password, client_id, client_secret):
    """
    Obtiene el token usando la API oficial OAUTH de SUNAT.
    """
    url_token = f"https://api-seguridad.sunat.gob.pe/v1/clientessol/{client_id}/oauth2/token/"
    username_completo = f"{ruc}{usuario}"

    payload = {
        "grant_type": "password",
        "scope": "https://api-sire.sunat.gob.pe",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username_completo,
        "password": password,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        response = await asyncio.to_thread(requests.post, url_token, data=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            return token, None

        return None, f"Error API SUNAT ({response.status_code}): {response.text}"
    except Exception as e:
        logger.exception("Error de conexion obteniendo token SUNAT para username=%s", username_completo)
        return None, f"Error de conexion con API SUNAT: {str(e)}"


async def procesar_y_guardar_comprobantes(data, user_id, periodo, db):
    registros = data.get("registros", [])
    if not registros and isinstance(data, list):
        registros = data

    if not registros:
        return []

    facturas_col = db["facturas"]
    facturas_procesadas = []

    for comprobante in registros:
        serie = str(comprobante.get("numSerieCDP", "") or "").strip().upper()

        if not (serie.startswith("F") or serie.startswith("E")):
            continue

        numero = comprobante.get("numCDP", "")
        ruc_emisor = comprobante.get("numDocIdentidadProveedor", "")
        if not ruc_emisor or ruc_emisor == "0":
            ruc_emisor = comprobante.get("numRuc", "")
        # Prioriza campos explícitos del PROVEEDOR para evitar tomar razón social del comprador.
        nombre_proveedor = (
            comprobante.get("desRazonSocialProveedor")
            or comprobante.get("nomRazonSocialProveedor")
            or comprobante.get("desProveedor")
            or comprobante.get("desRazonSocialEmisor")
            or comprobante.get("nomRazonSocialEmisor")
            or ""
        )
        serie_numero = f"{serie}-{numero}".strip()
        montos = comprobante.get("montos") or {}
        total = float(montos.get("mtoTotalCp", 0) or 0)
        igv = float(montos.get("mtoIGV", 0) or montos.get("mtoIgvIpm", 0) or 0)

        try:
            fecha_raw = comprobante.get("fecEmision", "")[:10]
            dt = datetime.strptime(fecha_raw, "%Y-%m-%d")
            
            # Validar que el comprobante pertenezca al periodo solicitado
            if dt.strftime("%Y%m") != periodo:
                continue
                
            fecha_emision = dt.strftime("%d/%m/%Y")
            fecha_anterior = (dt - timedelta(days=1)).strftime("%d/%m/%Y")
        except Exception:
            fecha_emision = "01/01/1970"
            fecha_anterior = "01/01/1970"

        filtro = {"user_id": user_id, "periodo": periodo, "serie_numero": serie_numero}
        payload_base = {
            "user_id": user_id,
            "periodo": periodo,
            "serie_numero": serie_numero,
            "estado_procesamiento": "sire_recibido",
        }
        payload_sync = {
            "ruc_emisor": ruc_emisor,
            "nombre_proveedor": nombre_proveedor,
            "fecha_emision": fecha_emision,
            "fecha_anterior": fecha_anterior,
            "total": total,
            "igv": igv,
            "tipo_operacion": "compras",
            "raw_data": json.dumps(comprobante, ensure_ascii=False),
        }

        res = await facturas_col.update_one(
            filtro,
            {
                "$setOnInsert": payload_base,
                "$set": payload_sync,
            },
            upsert=True,
        )
        if res.upserted_id:
            facturas_procesadas.append(serie_numero)

    return facturas_procesadas


def _obtener_credenciales_sunat(empresa):
    client_id = empresa.get("sunat_client_id") or (settings.SUNAT_CLIENT_ID or "").strip()
    client_secret = empresa.get("sunat_client_secret") or (settings.SUNAT_CLIENT_SECRET or "").strip()
    return client_id, client_secret


async def _renovar_token(empresa: dict, client_id: str, client_secret: str, users_col):
    """Desencripta la password y pide un token nuevo a SUNAT, persistiéndolo si tiene éxito.

    Compartido entre la obtención inicial del token y el retry ante un 401 en
    obtener_propuesta (antes duplicado casi verbatim en ambos puntos).
    """
    password = decrypt_password(empresa["password"]) if empresa.get("password") else ""
    sunat_token, error = await obtener_token_api_oficial(
        empresa["ruc"],
        empresa["usuario"],
        password,
        client_id,
        client_secret,
    )
    if sunat_token:
        await users_col.update_one({"_id": empresa["_id"]}, {"$set": {"sunat_token": sunat_token}})
    return sunat_token, error


async def obtener_propuesta(
    tenant_id: str,
    cliente_id: str,
    cuenta_id: str,
    periodo: str,
    db,
    user_db,
):
    users_col = user_db["sol_users"]
    empresa = await users_col.find_one(
        {
            "tenant_id": tenant_id,
            "cliente_id": cliente_id,
            "cuenta_id": cuenta_id,
        }
    )

    if not empresa:
        logger.warning(
            "No se encontro empresa en Mod_Facturas.sol_users tenant_id=%s cliente_id=%s cuenta_id=%s",
            tenant_id,
            cliente_id,
            cuenta_id,
        )
        raise Exception("Usuario no encontrado en Mod_Facturas.sol_users")

    user_id = str(empresa["_id"])
    sunat_token = empresa.get("sunat_token")
    client_id, client_secret = _obtener_credenciales_sunat(empresa)

    if not sunat_token:
        if not client_id or not client_secret:
            raise Exception("No se han configurado Client ID")

        sunat_token, error = await _renovar_token(empresa, client_id, client_secret, users_col)
        if not sunat_token:
            return None, f"Error al obtener token de API SUNAT: {error}"

    raw_url_api_sire = (settings.URL_SIRE_PROPUESTA or "").strip()
    if not raw_url_api_sire:
        raise Exception("URL no configurada en el entorno")
    url_api_sire = raw_url_api_sire.replace("{PERIODO}", periodo)

    headers = {
        "Authorization": f"Bearer {sunat_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    params = {"page": 1, "perPage": 100, "codTipoOpe": "1"}

    response = await asyncio.to_thread(requests.get, url_api_sire, headers=headers, params=params)

    if response.status_code == 401:

        if not client_id or not client_secret:
            raise Exception("El token expiro y no hay credenciales API configuradas para renovarlo.")

        sunat_token, error = await _renovar_token(empresa, client_id, client_secret, users_col)
        if not sunat_token:
            raise Exception(f"El token expiro y fallo la renovacion via API: {error}")

        headers["Authorization"] = f"Bearer {sunat_token}"
        response = await asyncio.to_thread(requests.get, url_api_sire, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        facturas = await procesar_y_guardar_comprobantes(data, user_id, periodo, db)
        await db["periodos"].update_one(
            {"user_id": user_id, "periodo": periodo},
            {"$set": {"estado": "terminado"}},
        )
        return facturas

    if response.status_code == 422:
        await db["periodos"].update_one(
            {"user_id": user_id, "periodo": periodo},
            {"$set": {"estado": "terminado"}},
        )
        return []

    logger.error(
        "Error SIRE no controlado user_id=%s periodo=%s status=%s body=%s",
        user_id,
        periodo,
        response.status_code,
        response.text[:1000],
    )
    raise Exception(f"Error {response.status_code}: {response.text}")


async def procesar_detalles_scraper(
    tenant_id: str,
    cliente_id: str,
    cuenta_id: str,
    periodo: str,
    db,
    user_db,
    debug: bool = False,
    headed: bool = False,
):
    from app.services.scraping_sunat import obtener_detalles_facturas_recibidas
    
    users_col = user_db["sol_users"]
    empresa = await users_col.find_one({
        "tenant_id": tenant_id,
        "cliente_id": cliente_id,
        "cuenta_id": cuenta_id
    })
    
    if not empresa:
        raise Exception("Usuario no encontrado")
        
    user_id = str(empresa["_id"])
    
    facturas_col = db["facturas"]
    cursor = facturas_col.find({
        "user_id": user_id, 
        "periodo": periodo,
        "detalle_compras_sunat": {"$exists": False}
    })
    
    facturas_pendientes = await cursor.to_list(length=100)
    if not facturas_pendientes:
        return {
            "mensaje": "No hay facturas pendientes de extraer detalles",
            "facturas_procesadas": 0,
            "facturas_con_detalles_encontrados": 0
        }
        
    resultados = await obtener_detalles_facturas_recibidas(
        tenant_id, cliente_id, cuenta_id, facturas_pendientes, user_db, debug, headed
    )
    
    actualizadas = 0
    for serie_numero, detalle in resultados.items():
        if detalle:
            await facturas_col.update_one(
                {"user_id": user_id, "periodo": periodo, "serie_numero": serie_numero},
                {"$set": {"detalle_compras_sunat": detalle}}
            )
            actualizadas += 1
            
    return {
        "mensaje": "Proceso completado",
        "facturas_procesadas": len(facturas_pendientes),
        "facturas_con_detalles_encontrados": actualizadas
    }

