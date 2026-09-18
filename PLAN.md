# Plan — Plataforma Sire

Última revisión: 18 de septiembre de 2026. Documento vivo: describe qué hace hoy la plataforma, qué queda fuera y cuál es el camino inmediato. Los detalles técnicos viven en [docs/](docs/README.md).

## Qué hace hoy

La plataforma prepara el Registro de Compras (RCE) y el Registro de Ventas (RVIE) de una empresa para el contador, a partir de lo que SUNAT ya tiene:

1. **Sincroniza la propuesta** de ambos libros desde la API SIRE (paginada) y, para compras, la reconstruye desde el ZIP oficial de un ticket antes de exportar. Concilia cantidad y totales contra el resumen oficial del RCE.
2. **Extrae el detalle y el PDF** de cada comprobante del portal SOL con Playwright, como job encolado por empresa: bandejas por tipo de documento para las series F/B y el módulo SEE-SOL para las series E (facturas E001 y boletas EB01, verificadas con datos reales).
3. **Construye la glosa** de forma determinista: descripciones del detalle, la leyenda del comprobante cuando los ítems no describen nada, o el texto manual del usuario. Cada comprobante lleva un **estado de glosa** (con glosa, sin glosa, en evaluación, pendiente) según lo que SUNAT publica de su tipo; los tipos que SUNAT no publica no se consultan.
4. **Entrega**: Excel en la plantilla oficial de Contasis por libro (con columnas Observación y Estado glosa y hoja de anulados), PDF del listado, ZIP de respaldos con manifiesto, ZIP completo de compras y ventas, reporte mensual asociado con control de correlatividad, NPD de detracciones y reporte de auditoría con fuentes por comprobante.
5. **Panel web** en React con todo lo anterior, tema claro/oscuro y seguimiento de jobs.
6. **Acceso con cuenta de Google**, con una lista de correos autorizados en el entorno. La sesión es de una persona, no de una empresa: desde dentro se ven todas las empresas registradas y se cambia entre ellas sin volver a iniciar sesión. Las credenciales SOL siguen guardadas y cifradas, pero solo para hablar con SUNAT.

## Alcance por tipo de comprobante

Ver [docs/flujo/05-glosa-y-estado.md](docs/flujo/05-glosa-y-estado.md) y el catálogo en `app/domain/catalogos.py`:

- **Con detalle en SUNAT (17)**: 01, 03, 07 verificados; 08, 13, 14, 18, 19, 23, 29, 34, 35, 36, 42, 64, 87, 88 a la espera de casos reales del cliente. `scripts/informe_tipos.py` genera la evidencia por tipo cuando lleguen.
- **Sin detalle en SUNAT (35)**: los 23 del alcance original, el 30 (reclasificado con dos casos reales) y once de los doce que estaban en evaluación.
- **En evaluación (1)**: 02, recibos por honorarios; SUNAT los publica por otro módulo de SOL.
- **Boletas recibidas (compras/03)** de serie B: el portal no tiene bandeja «BVE Recibidas»; se entregan sin glosa. Las EB01 recibidas sí se consultan.

## Fuera de alcance

- **Escritura contra el SIRE**: aceptar, reemplazar y generar el registro. Requiere el flujo por ticket de SUNAT y el formato del archivo de reemplazo, aún sin confirmar.
- **Conciliación Contasis ↔ SIRE**: Contasis entra sólo como plan de cuentas y sale como plantilla; no hay parser de sus registros ni motor de conciliación.
- **Campos de auditoría refinados**: pendientes de especificación del cliente.
- **Análisis con IA**: retirado en septiembre de 2026. La glosa es determinista.

## Próximos pasos

Según el cronograma de cierre (12 al 22 de septiembre de 2026):

1. **Casos del cliente** para los 14 tipos que requieren casos y un RUC que emita boletas por OSE/PSE (series B) para verificar el criterio de documento del receptor.
2. **Despliegue en Google Cloud**: proyecto, máquina virtual, contenedores de aplicación, base de datos y proxy HTTPS, secretos, migración de datos, publicación de la web, respaldos y prueba de humo. El cliente OAuth de Google necesita el dominio de producción en sus orígenes autorizados, y el entorno, `GOOGLE_CLIENT_ID` y `GOOGLE_ALLOWED_EMAILS`.
3. **Pruebas finales** con datos reales del cliente en producción y validación del Excel Contasis y del reporte por su contador.
4. Después del cierre: decidir si se construye la ruta de recibos por honorarios (02) y si la leyenda debe complementar al ítem además de sustituirlo cuando está vacío.

## Reglas de trabajo

- `domain/` no importa `app.db`, `app.repositories` ni `requests`; todo lo que entra son estructuras de datos.
- Un cambio en `serializar` debe reflejarse en `ComprobanteResponse`: hay un test que lo exige.
- No editar `.py` mientras corre un job de scraping en desarrollo (`--reload` mata el navegador).
- Los enlaces de la documentación al código nombran archivo y función, nunca línea.
