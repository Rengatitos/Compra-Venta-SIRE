# Endpoints — SIRE

Prefijo `/sol-users/{user_id}/periodos/{periodo}/propuesta`, montado en [main.py](../../app/main.py:117). Router en [sire.py](../../app/api/routes/sire.py).

| Método | Path completo | Función | Auth |
|---|---|---|---|
| GET | `/sol-users/{user_id}/periodos/{periodo}/propuesta/` | [get_sire_propuesta](../../app/api/routes/sire.py:20) | verify_user, con límite de tasa |
| POST | `/sol-users/{user_id}/periodos/{periodo}/propuesta/scrape-detalles` | [post_scrape_detalles](../../app/api/routes/sire.py:93) | verify_user, con límite de tasa |

## Nota sobre la resolución del usuario objetivo

Aunque el path de ambos endpoints incluye el identificador de usuario y el periodo, estos handlers en realidad reciben también los identificadores de tenant, cliente y cuenta como parámetros propios, y resuelven al usuario buscando esa combinación en la colección de usuarios SOL — no usan el identificador de usuario del path para nada. Esto implica que la autorización real de estos dos endpoints es solo verify_user (cualquier token válido), sin la verificación adicional de "mismo usuario" que sí tienen la mayoría de las demás rutas. El detalle de esta decisión y su implicación de seguridad está en [autenticación — rutas sin protección de identidad explícita](../arquitectura/autenticacion.md).

**get_sire_propuesta** sincroniza, de forma síncrona (bloqueando la petición HTTP hasta terminar), la propuesta de comprobantes de compra desde la API oficial de SIRE, y guarda o actualiza las facturas correspondientes. El detalle completo del proceso —resolución de credenciales, manejo y renovación del token OAuth, y las reglas de procesamiento de cada comprobante— está en [flujo de sincronización SIRE](../flujo/03-sincronizacion-sire.md).

**post_scrape_detalles** dispara en segundo plano (sin bloquear la respuesta HTTP, que se devuelve de inmediato indicando que el proceso fue iniciado) el scraping con Playwright del detalle de ítems de las facturas que aún no lo tienen. El detalle completo está en [flujo de scraping de detalle](../flujo/04-scraping-detalle.md).
