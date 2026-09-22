# Cronograma ampliado: despliegue, pruebas y web app del bot

Continúa el cronograma de cierre (`Sire_Docs/Cronograma.xlsx`) **desde la Fase 2**, con las mismas tareas y responsables, y añade la **Fase 4: la web app del bot**. Del 17 de septiembre al 6 de octubre de 2026. La decisión de canal está en `Canal_WhatsApp_vs_PWA.xlsx` y los costos en [costos-canales.md](costos-canales.md).

| Fase | Fechas | Estado |
|---|---|---|
| Fase 2 — Despliegue en Google Cloud | 17 a 19-sep | Ya planificada, sin cambios |
| Fase 3 — Pruebas finales y entrega | 20 a 22-sep | Ya planificada, sin cambios |
| **Fase 4 — Web app del bot (PWA)** | **23-sep a 6-oct** | **Nueva** |

## Unidad de medida

**Una sesión = 4 horas de trabajo asistido.** Es la unidad real de este equipo, calibrada contra un hecho verificable: la sesión del 19 de septiembre produjo `sire-bot` completo, 10.652 líneas de TypeScript en 110 archivos y 241 tests.

## Tiempo ya gastado

| Proyecto | Periodo | Resultado |
|---|---|---|
| **Sire** (backend + panel web) | 25-ago a 19-sep-2026, 68 commits en 18 días con actividad | ~32.000 líneas, 545 tests, 46 endpoints |
| **sire-bot** | 19-sep-2026, una sesión de 4 h | 10.652 líneas, 241 tests, 11 rutas HTTP, workflow de 8 pasos |

Lo que el bot ya resuelve y no se vuelve a tocar: extracción de la foto con Gemini validada contra esquema, normalización de montos, fechas, series y RUC con paridad contra `app/domain/comprobante.py`, idempotencia por clave natural, deduplicación por hash de imagen, reintentos con backoff hacia Sire, borrado de EXIF y purga de imágenes a los 30 días. Y las rutas `/api/bot/*` con el JWT de dispositivo, que son exactamente lo que la PWA necesita.

Lo que no: nada de esto ha tocado el Sire real. Los tres endpoints que el bot necesita tienen **cero líneas escritas**.

## Fase 4: cuánto demoraría

| # | Tarea | Responsable | Horas |
|---|---|---|---|
| 21 | Prueba de extracción con fotos reales de comprobantes y ajuste del prompt | Cinver | 4 |
| 22 | Endpoints en Sire: código de vinculación, canje y comprobantes externos | Camila | 6 |
| 23 | Ampliación de la máquina a e2-medium y contenedor del bot con volumen para imágenes | Camila | 3 |
| 24 | Pantalla de vinculación en el panel web: código de 6 dígitos de un solo uso | Cinver | 2 |
| 25 | PWA: cámara, compresión en el navegador y envío al bot | Cinver | 5 |
| 26 | PWA: cola offline en IndexedDB con Background Sync e indicador de pendientes | Cinver | 4 |
| 27 | PWA: confirmación por endpoint determinista e historial de envíos | Cinver | 3 |
| 28 | Verificación end-to-end contra el Sire real, reemplazando el stub | Cinver y Camila | 4 |
| 29 | Vinculación de las 10 empresas y piloto con las dos primeras | Cinver y Camila | 2 |
| | **Total** | | **33** |

**33 horas, unas 8 sesiones, repartidas en 10 días hábiles:** 21 horas para Cinver y 12 para Camila, alrededor de 2 horas diarias cada uno trabajando en paralelo. Entra en las dos semanas que da el cliente, sin margen sobrante.

Las dos tareas de mayor riesgo van primero a propósito: la prueba con fotos reales (21) y los endpoints en Sire (22) arrancan el mismo 23 de septiembre. Si alguna falla, quedan nueve días para reaccionar en lugar de dos.

## Calendario de la Fase 4

| # | Tarea | Responsable | Días |
|---|---|---|---|
| 21 | Prueba de extracción con fotos reales | Cinver | 23 a 24-sep |
| 22 | Los 3 endpoints en Sire | Camila | 23 a 25-sep |
| 23 | Máquina ampliada y contenedor del bot | Camila | 28-sep |
| 24 | Pantalla de vinculación en el panel web | Cinver | 28-sep |
| 25 | PWA: cámara, compresión y envío | Cinver | 29 a 30-sep |
| 26 | PWA: cola offline con Background Sync | Cinver | 1 a 2-oct |
| 27 | PWA: confirmación e historial | Cinver | 2-oct |
| 28 | Verificación end-to-end contra Sire real | Cinver y Camila | 5-oct |
| 29 | Vinculación de las 10 empresas y piloto | Cinver y Camila | 6-oct |

## Hitos

| Fecha | Hito |
|---|---|
| 19-sep | Plataforma en producción en Google Cloud con prueba de humo aprobada |
| 21-sep | Aceptación del contador sobre el Excel Contasis y el reporte |
| 22-sep | Entrega y cierre del alcance actual |
| 24-sep | La extracción funciona sobre fotos reales de cámara, o se sabe cuánto hay que corregir |
| 25-sep | Los 3 endpoints del bot existen en Sire |
| 2-oct | PWA completa: captura, cola offline y confirmación |
| 5-oct | Primer comprobante real entra desde la PWA hasta Sire |
| 6-oct | Las 10 empresas vinculadas y entrega de la Fase 4 |

## Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| La Fase 3 no cierra el 22 de septiembre | La Fase 4 arranca tarde y se corre entera | Cerrar las incidencias de la Fase 3 antes de empezar la PWA |
| Gemini falla sobre fotos de cámara reales | La tarea 21 pasa de 4 a 12 horas y come el margen | Va primera, el 23-sep: quedan 9 días para reaccionar |
| La e2-small de 2 GB no aguanta Sire más el bot | Ampliar a e2-medium, unos USD 15 más al mes | Previsto en la tarea 23, no es un imprevisto |
| Los 3 endpoints son código nuevo sobre una colección nueva | Retrasa la verificación end-to-end | El contrato está especificado campo por campo, con su stub |
| La cola offline solo se prueba con WiFi de oficina | Se descubre en campo, con el cliente delante | Probar con datos móviles limitados y en modo avión antes del piloto |
| Una de las dos personas no está disponible | La Fase 4 no entra en dos semanas | Recortar el historial y los botones de corrección de la PWA |

## Fase 5, opcional y sin plazo

**WhatsApp: unas 10 horas.** El 70 % del bot no depende del canal, así que se reduce a la capa de canal más el alta en Meta Business. Conviene reabrirlo si el cliente suma usuarios que no controla, si los vendedores terminan mandando las fotos por WhatsApp de todos modos, o si hace falta avisar al usuario sin que abra la app.
