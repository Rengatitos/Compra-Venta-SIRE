# WhatsApp e inventario documental de SIRE

Integrado con **FastAPI, MongoDB y React existentes**. `chatbot_whatsapp` consume la API
por HTTP; no importa el backend ni accede a Mongo. Empresas, JWT y base de datos siguen
siendo los del proyecto. Redis/Celery ejecutan el OCR local fuera del webhook.

```text
Twilio → chatbot_whatsapp:9008 → API SIRE:9007 → MongoDB → workers OCR
                                      ↑                     ↓
                                 React: inventario, lotes y revisión
```

## Arranque

Desde la raíz, usando el `.env` existente del backend y `chatbot_whatsapp/.env`:

```bash
docker compose -f docker-compose.yml -f chatbot_whatsapp/docker-compose.yml up --build -d
npm run dev --prefix frontend
```

Sin contenedores, con Redis disponible, ejecutar cada proceso en una terminal:

```bash
uv sync --extra captura
uv run uvicorn app.main:app --host 127.0.0.1 --port 9007
uv run uvicorn chatbot_whatsapp.main:app --host 127.0.0.1 --port 9008 --no-access-log
uv run celery -A app.workers.captura worker --loglevel=WARNING
uv run celery -A app.workers.captura beat --loglevel=WARNING
npm run dev --prefix frontend
```

Para Celery en Windows usar `--pool=solo`; para procesamiento paralelo, contenedores Linux.
MongoDB debe ser un replica set con transacciones, como Atlas. Los índices nuevos se crean
al iniciar la API; no se migran ni reemplazan colecciones SIRE existentes.
Para el contenedor MongoDB local existente, consulta [MONGO_LOCAL.md](MONGO_LOCAL.md).
El Compose de captura toma `MONGO_URI` del `.env` de la raíz para los tres procesos
(API, worker y beat); no reemplaza esa conexión por una dirección fija.

## Activar WhatsApp

1. Expón el puerto **9008** mediante ngrok.
2. Configura en Twilio el webhook POST a la URL HTTPS de `TWILIO_WEBHOOK_URL`, terminada
   en `/webhooks/twilio/whatsapp`. Si cambia el dominio, actualiza `.env` y reinicia la API.
3. Inicia sesión en React y autoriza el número del cliente desde **Lotes y WhatsApp**.
4. En Sandbox, el cliente debe unirse también al Sandbox de Twilio.
5. Envía `HOLA`, una fotografía o `LOTE` desde el número autorizado.

`TWILIO_PHONE_NUMBER` es el **emisor de Twilio**, que llega como `To` en el webhook.
En Sandbox es `+14155238886`; un número comprado en Twilio no lo sustituye.
El teléfono del cliente se autoriza desde React. Si cambias el emisor o las credenciales,
recrea los servicios con el comando de arranque para que carguen el nuevo entorno.

### Diagnóstico

- `403 Destino inválido`: `TWILIO_PHONE_NUMBER` no coincide con el `To` de Twilio.
- `403 Firma inválida`: revisar el token y la URL pública exacta, sin desactivar la firma.
- `503 MONGO_TRANSACTIONS_REQUIRED`: MongoDB no admite transacciones; habilitar un replica
  set en la base existente. La captura conserva transacciones para evitar escrituras parciales.
- Mensaje de teléfono no autorizado: volver a autorizar el número del cliente en su empresa.

El cliente conserva la firma original; la API la verifica sobre la URL pública configurada.
Mantén `TWILIO_VALIDATE_SIGNATURE=true`. Las credenciales sólo van en `.env`, excluido del
repositorio y de la imagen Docker. `.env.example` documenta todas las opciones.

## Uso

- `/comprobantes`: inventario, periodos, filtros, cargas y exportación CSV.
- `/comprobantes/:id`: original, evidencia, edición, revisión de periodo, confirmación e historial.
- `/lotes`: creación de lotes, consulta y autorización del teléfono.
- `/lotes/:id`: documentos del lote, cierre y confirmación de válidos.

Comandos: `REGISTRAR`, `FACTURA`, `BOLETA`, `LOTE`, `MASIVO`, `FIN`, `ESTADO`,
`PENDIENTES`, `CONFIRMAR`, `CONFIRMAR VALIDOS`, `CORREGIR`, `CANCELAR`, `AYUDA`.
También se aceptan números 1–6. Un lote pide primero el periodo, por ejemplo `SEPTIEMBRE 2026`.
La revisión compleja se hace en el inventario. Una imagen sin lote se recibe individualmente.

Por defecto se utiliza texto, incluido Sandbox. Las variables opcionales
`TWILIO_SINGLE_CONTENT_SID` y `TWILIO_BATCH_CONTENT_SID` permiten plantillas Content con
botones, variable `{{1}}` para el resumen y payloads de los comandos anteriores. Si Twilio
rechaza una plantilla por elegibilidad, se intenta el mensaje textual.

La documentación técnica, límites y pruebas están en [IMPLEMENTACION.md](IMPLEMENTACION.md).
