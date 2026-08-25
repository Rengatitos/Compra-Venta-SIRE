# Endpoints — Analysis

Prefijo `/sol-users/{user_id}/periodos/{periodo}/analisis`, montado en [main.py](../../app/main.py:122). Router en [analysis.py](../../app/api/routes/analysis.py).

| Método | Path completo | Función | Auth |
|---|---|---|---|
| POST | `/sol-users/{user_id}/periodos/{periodo}/analisis/` | [ejecutar_analisis](../../app/api/routes/analysis.py:22) | require_same_user, con límite de tasa |

**ejecutar_analisis** ejecuta el análisis contable con IA sobre las facturas pendientes del periodo. Acepta PDFs opcionales, enviados como parte del mismo formulario, que se usan como contexto adicional para la clasificación (RAG ad-hoc); si no se adjuntan, se usan los fragmentos ya indexados previamente para ese usuario. También acepta un parámetro de rubro de negocio, con un valor general por defecto cuando no se especifica.

El proceso completo de clasificación —los dos niveles de contexto (normativa global y referencias del usuario), el prompt enviado a Gemini, y las reglas de negocio aplicadas— está documentado en [flujo de análisis con IA](../flujo/05-analisis-ia.md).
