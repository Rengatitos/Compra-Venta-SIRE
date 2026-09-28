# Cola durable de trabajos

Todo lo pesado corre en segundo plano, en una cola que vive en Mongo: descargas SIRE, detalle y PDF del portal SOL, detracciones, clasificación con IA, alta de empresas, empaquetado del ZIP y correos. El contador puede cerrar la página y la API puede reiniciarse sin que se pierda nada.

Código: [app/services/cola/](../../app/services/cola/) (`encolar`, [worker.py](../../app/services/cola/worker.py), [tareas.py](../../app/services/cola/tareas.py)) y las operaciones atómicas de [repositories/jobs.py](../../app/repositories/jobs.py).

## Cómo funciona

- **Encolar** (`cola.encolar`) inserta en `jobs` un documento `gestionado` con todo lo necesario para ejecutarlo: tipo, RUC, periodo, libro y `parametros`. No hay closures en memoria. Luego despierta al worker.
- **El worker** arranca en el `lifespan` de la API como `COLA_TRABAJADORES` corrutinas (2 por defecto: cada descarga abre un Chromium de ~0,5 GB). Cada una:
  1. toma con `find_one_and_update` el `pendiente` más antiguo cuyo turno llegó (`siguiente_intento_en ≤ ahora`) y cuyo carril esté libre; lo marca `en_progreso` y suma un intento;
  2. ejecuta el manejador de su tipo (`tareas.manejador`), que vuelve a leer la empresa de Mongo;
  3. actualiza `latido_en` cada `COLA_LATIDO_S` mientras corre.
- **Carriles** (`cola`): dos jobs del mismo carril no corren a la vez.
  - El RUC, para lo que entra con la sesión SOL (detalle, PDFs, detracciones, credenciales, alta): la sesión es única por usuario y dos Chromium a la vez se la invalidan mutuamente.
  - `sire:{RUC}` para las descargas por API.
  - `clasificador`, uno global: el motor serializa sus llamadas a Gemini.
  - `correo` para los envíos. Sin carril (empaquetado), corre en paralelo.

## Reintentos

| Qué pasa | Resultado |
|---|---|
| El manejador termina | `completado` con su `resultado` |
| `ErrorPermanente`, clave SOL rechazada (`CredencialesSolError`), aplicación sin SIRE (`SinRecursoSire`), tipo sin manejador | `fallido` al primer intento. Reintentar no arreglaría nada, y con la clave SOL podría bloquear al usuario |
| Cualquier otra excepción, o `ErrorTransitorio` | vuelve a `pendiente` con `siguiente_intento_en = ahora + COLA_BACKOFF_BASE_S · 2^(n-1)` (techo `COLA_BACKOFF_MAX_S`) hasta `COLA_MAX_INTENTOS`; después, `fallido` |

Cada job guarda `intentos`, `max_intentos`, `ultimo_intento_en`, `siguiente_intento_en`, el `error` del último y `historial_errores` con uno por intento. `POST /jobs/{id}/reintentar` devuelve un fallido a la cola con el contador a cero.

## Reinicios

Un job `en_progreso` cuyo latido pasó de `COLA_LATIDO_VENCIDO_S` murió con su proceso. El worker lo revisa al arrancar y cada minuto (`recuperar_huerfanos`): si le quedan intentos vuelve a `pendiente`, si no queda `fallido`.

Solo se miran los jobs `gestionado`. El Mongo local lo comparte otra copia de la API (la de la rama del bot), cuyos jobs no son de este worker; por la misma razón `marcar_interrumpidos` ya no toca los gestionados. Una segunda copia de esta API contra el mismo Mongo debe arrancar con `COLA_HABILITADA=false` para no competir por los mismos trabajos.

## Límites

El worker vive en el proceso de la API, que corre con un solo worker de Uvicorn. Con varias réplicas la toma seguiría siendo atómica (es una sola operación en Mongo), pero los carriles se reservan en memoria y habría que llevarlos también a Mongo.
