# Modelo de datos — empresas

Una empresa (RUC ante SUNAT). Poblada por [crear_empresa](../../app/api/v1/routes/empresas.py).

| Campo | Tipo | Descripción |
|---|---|---|
| `_id` | ObjectId | Identificador de Mongo. Referenciado como `empresa_id` (string) en el resto de las colecciones. |
| `ruc` | str | 11 dígitos, validado en [EmpresaBase](../../app/schemas/empresa.py). Único — índice único. |
| `nombre` | str \| None | Nombre visible en el selector de cuentas. Opcional: el documento no guarda razón social, así que sin él la lista son solo RUC. |
| `usuario` | str | Usuario SOL. |
| `password` | str | Contraseña SOL cifrada con Fernet. Ver [cifrado](../arquitectura/cifrado.md). |
| `sunat_token` | str \| None | Token OAuth de la API SIRE, cacheado tras la primera obtención o renovación. |
| `sunat_client_id`, `sunat_client_secret` | str \| None | Credenciales propias del cliente OAuth de la empresa. Si son `None`, se usan las globales de `SUNAT_CLIENT_ID`/`SUNAT_CLIENT_SECRET`. |
| `fecha_creacion` | str, ISO con zona horaria UTC | Escrita por [repo_empresas.crear](../../app/repositories/empresas.py). |
| `ciiu`, `rubro` | str \| None | Guardados al completar el alta: el CIIU del token SIRE o, si no lo trae, el de la actividad principal de la ficha RUC, y el rubro que se deriva de él ([rubro.py](../../app/domain/rubro.py)). Las empresas de antes no los tienen y el rubro se sigue deduciendo del token. |
| `registro` | dict \| None | Trazabilidad del alta: `{modalidad: individual o masiva, por: correo, fecha, carga_id}`. |
| `correos_notificacion` | list[str] | A quién se envían los resultados de las [solicitudes](solicitudes.md). Normalizados, máximo 10. |

`usuario` y `password` son credenciales **SOL ante SUNAT** y no intervienen en el acceso al panel, que se hace con una cuenta de Google. No hay colección de usuarios: la lista de correos autorizados vive en el entorno (ver [autenticación](../arquitectura/autenticacion.md)).

Índice: único sobre `ruc`.
