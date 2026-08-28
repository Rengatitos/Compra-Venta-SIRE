# Rate limiting

Los límites de tasa se implementan con `slowapi`, indexados por IP remota ([get_remote_address](../../app/main.py:8)). Cada router que necesita límites propios instancia su propio `Limiter` local (mismo `key_func`), y el manejador de excepción se registra una sola vez en [main.py](../../app/main.py:65).

| Endpoint | Límite | Razón |
|---|---|---|
| `POST /api/v1/empresas` | 5/minuto | Evitar registro masivo de empresas. |
| `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/propuesta` | 10/minuto | La API oficial de SUNAT también tiene sus propios límites; evita saturarla desde un solo cliente. |
| `POST /api/v1/empresas/{ruc}/periodos/{periodo}/analisis` | 5/minuto | Cada llamada dispara una o más peticiones a Gemini, que tiene costo y límites propios. |
| `POST /api/v1/empresas/{ruc}/periodos/{periodo}/detalle` | 5/minuto | Cada llamada lanza un navegador Playwright completo contra el portal SOL. |

El resto de los endpoints no tiene límite propio.

Si se excede un límite, `slowapi` devuelve `429 Too Many Requests` a través de [_rate_limit_exceeded_handler](../../app/main.py:64), registrado como manejador de `RateLimitExceeded`.
