# Endpoints — Apaclla Bot (sire-bot)

Integración con [sire-bot](../../../sire-bot), el chat donde una persona manda la foto de un Yape, Plin, boleta o factura. El bot extrae los datos, los confirma con la persona y los registra aquí como **comprobante externo**. El contrato del lado del bot está en `sire-bot/docs/sire-contract.md`.

## Autenticación del bot: `X-Api-Key`

El bot no usa la sesión de Google del panel. Se identifica con la cabecera `X-Api-Key`, que se compara en tiempo constante contra `SIRE_BOT_API_KEY` ([servicio.py](../../app/core/servicio.py)). La misma cadena va en el `SIRE_API_KEY` del `.env` del bot.

| Situación | Respuesta |
|---|---|
| `SIRE_BOT_API_KEY` sin configurar | `503`: la integración falla cerrada |
| Falta la cabecera | `401` |
| Clave incorrecta | `403` |

## `POST /api/v1/empresas/{ruc}/codigos-vinculacion`

[generar_codigo](../../app/api/v1/routes/vinculacion.py). **Requiere sesión del panel.** Genera un código de 6 dígitos para vincular un dispositivo del bot con la empresa. Responde `201 {"codigo": "483921", "expira_en": "2026-09-19T20:00:00Z"}`.

- Dura 10 minutos y sirve una sola vez.
- Generar uno nuevo anula los anteriores que no se hayan canjeado.
- Solo se guarda su sha256 (colección `codigos_vinculacion`, con TTL).
- Límite: 10/minuto.

Se genera desde **Ajustes, en «Vinculación con Apaclla Bot»**.

## `POST /api/v1/empresas/{ruc}/codigos-vinculacion/canjear`

[canjear_codigo](../../app/api/v1/routes/vinculacion.py). **Solo el bot (`X-Api-Key`).** Body `{"codigo": "483921", "dispositivo_id": "web-…"}`. Responde `200 {"empresa": {"ruc", "nombre"}}`; si la empresa no tiene nombre, devuelve `RUC <ruc>`.

- `400`: código inválido, vencido o de otra empresa.
- `409`: el código ya se canjeó.
- `404`: el RUC no está registrado.

Límite: 10/minuto por IP y RUC. Todo el tráfico del bot sale de la misma IP, así que el límite se cuenta por empresa para frenar la fuerza bruta sobre 6 dígitos.

## `POST /api/v1/empresas/{ruc}/comprobantes-externos`

[recibir](../../app/api/v1/routes/comprobantes_externos.py). **Solo el bot.** Recibe el comprobante confirmado (`ComprobanteExternoCreate`, ver [schema](../../app/schemas/comprobante_externo.py)).

Reglas de validación:
- Los montos llegan como texto con dos decimales (`"1234.50"`), nunca como número.
- Un `voucher` exige `nro_operacion` y `tipo_cp = "00"`.
- Un `comprobante` exige `serie` y `numero`.
- `imagen.contenido_base64` (opcional) trae la foto. Su sha256 tiene que coincidir con `imagen.sha256`, y el formato (JPEG, PNG o WEBP, hasta 10 MB) se decide por los bytes, no por el `mime` declarado.

Respuestas:

| Código | Cuándo |
|---|---|
| `201 {id, ruc, periodo, estado: "recibido", creado_en}` | Comprobante nuevo |
| `200` (mismo cuerpo) | El `id_externo` ya existía: reintento idempotente |
| `409 {detail, comprobante_externo_id}` | El mismo voucher (`fuente` + `nro_operacion`) o la misma boleta o factura (`libro` + `tipo_cp` + `serie` + `numero`) ya entró con otro `id_externo` |
| `422` | Body inválido o foto que no cuadra |

El `periodo` sale de `fecha_operacion` (`YYYYMM`). Límite: 120/minuto.

## `GET /api/v1/empresas/{ruc}/comprobantes-externos`

[listar](../../app/api/v1/routes/comprobantes_externos.py). **Requiere sesión.** Es la base de la página **Externos** del panel.

- Filtros: `libro`, `periodo` (YYYYMM), `fuente`, `limit` (hasta 100) y `skip`.
- Devuelve `{items, total, periodos}`, donde `periodos` son los periodos con externos, para el selector.
- Los montos salen como texto.

## `GET /api/v1/empresas/{ruc}/comprobantes-externos/{id}`

[obtener](../../app/api/v1/routes/comprobantes_externos.py). Acepta la sesión del panel **o** la clave del bot. Si llega `X-Api-Key` se trata como el bot, y una clave mala es `403`: no se prueba con el JWT. `404` si no existe o es de otra empresa.

## `GET /api/v1/empresas/{ruc}/comprobantes-externos/{id}/imagen`

[imagen](../../app/api/v1/routes/comprobantes_externos.py). **Requiere sesión.** Devuelve la foto con su `Content-Type`. Da `404` si el comprobante llegó sin foto o es de otra empresa.

Ver también [modelo de datos: comprobantes externos](../modelo-datos/comprobantes-externos.md).
