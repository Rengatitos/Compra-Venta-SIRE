# Modelo de datos — empresas

Una empresa (RUC ante SUNAT). Poblada por [crear_empresa](../../app/api/v1/routes/empresas.py:29).

| Campo | Tipo | Descripción |
|---|---|---|
| `_id` | ObjectId | Identificador de Mongo. Referenciado como `empresa_id` (string) en el resto de las colecciones. |
| `ruc` | str | 11 dígitos, validado en [EmpresaBase](../../app/schemas/empresa.py:5). Único — índice único. |
| `usuario` | str | Usuario SOL. |
| `password` | str | Contraseña SOL cifrada con Fernet. Ver [cifrado](../arquitectura/cifrado.md). |
| `sunat_token` | str \| None | Token OAuth de la API SIRE, cacheado tras la primera obtención o renovación. |
| `sunat_client_id`, `sunat_client_secret` | str \| None | Credenciales propias del cliente OAuth de la empresa. Si son `None`, se usan las globales de `SUNAT_CLIENT_ID`/`SUNAT_CLIENT_SECRET`. |
| `fecha_creacion` | str, ISO con zona horaria UTC | Escrita por [repo_empresas.crear](../../app/repositories/empresas.py:27). |

`rubro` **no se persiste**: se calcula al vuelo en cada respuesta, deduciéndolo del CIIU dentro de `sunat_token` (ver [rubro.py](../../app/domain/rubro.py)).

Índice: único sobre `ruc`.
