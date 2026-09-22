# Canal de captura: PWA propia vs WhatsApp API

Documento de decisión. El bot que lee fotos de comprobantes (`sire-bot`) está construido y probado, pero falta decidir por qué canal llegan esas fotos. Los costos están en [costos-canales.md](costos-canales.md) y los plazos en [cronograma.md](cronograma.md).

## El escenario real

| Dato | Valor | Qué implica |
|---|---|---|
| Empresas | **10, fijas y cerradas** | No hay curva de adopción ni usuarios desconocidos |
| Usuarios | **Una persona por empresa** | 10 vinculaciones en total, una sola vez |
| Dispositivos | **Solo Android** | La cola offline funciona completa, sin las limitaciones de Safari |
| Ubicación | **Zonas rurales** | Conectividad intermitente: es la restricción que manda el diseño |
| Plazo | **2 semanas** | Ningún plazo de terceros cabe dentro |
| Cuenta de Meta | **No existe** | Verificación de negocio, método de pago y plantillas partirían de cero |

## Por qué una PWA y no una app de tienda

Publicar en Google Play y App Store resolvía un problema que aquí no existe —llegar a usuarios desconocidos— y a cambio traía plazos que no controlamos. Con una PWA desaparecen todos de golpe:

| Lo que se evita | Por qué importa aquí |
|---|---|
| USD 99/año de Apple y USD 25 de Google Play | Costo recurrente que no compra nada con 10 usuarios conocidos |
| Regla de 12 probadores durante 14 días | Bloqueaba la publicación justo dentro del plazo de dos semanas |
| Revisión de App Store y de Play | Días de espera por cada cambio, incluida cada corrección |
| Verificación de desarrollador de Android | Google la vuelve obligatoria para instalar fuera de Play; global en 2027 |
| Builds nativos y firmas | Sin EAS, sin certificados, sin dos artefactos que mantener |

La distribución pasa a ser **un enlace y "añadir a pantalla de inicio"**. Actualizar es publicar: el usuario recibe la versión nueva al abrir, sin pasar por nadie.

Técnicamente también baja el riesgo: la PWA es una aplicación Vite que reusa el stack del panel web de Sire y consume los `/api/bot/*` que **ya están escritos y probados**. La cámara se resuelve con `<input type="file" accept="image/*" capture="environment">`, que Chrome en Android soporta sin matices.

## Qué se aprovecha de lo ya construido

`sire-bot` son 5.414 líneas de TypeScript y 241 tests. Frente a este canal:

| Capa | Líneas | Estado |
|---|---|---|
| `src/domain/` — normalización de montos, fechas, series, RUC | 1.002 | Se usa tal cual |
| `src/db/` — enlaces, imágenes, envíos, idempotencia | 878 | Se usa tal cual |
| `src/mastra/` — agente, extractor de visión, workflow de 8 pasos | 1.338 | Se usa tal cual |
| `src/services/` — imagen, envío a Sire, reintentos | 1.107 | Se usa tal cual |
| `src/http/` — rutas `/api/bot/*` | 524 | **Ya es exactamente lo que la PWA necesita** |
| `src/auth/` — JWT de dispositivo y refresh rotativo | 252 | **Ya es exactamente lo que la PWA necesita** |

Este es el argumento que más pesa en el plazo: **la ruta PWA no descarta una sola línea de lo construido**. Ir primero por WhatsApp obligaría a apartar las 776 líneas de `http/` y `auth/` y escribir una capa de canal nueva, con Meta de por medio y dos semanas encima.

## Lo que el entorno rural obliga a diseñar

No es una app normal con mala señal: la mala señal es el caso normal.

1. **Comprimir en el navegador antes de subir.** Una foto de cámara pesa 3-5 MB; por una red rural eso no llega. Redimensionar a 1600 px y JPEG 0,7 en un canvas la deja en ~200 KB. El bot ya reescala, pero lo hace *después* de recibirla: hay que hacerlo antes de que salga del teléfono.
2. **Cola offline en IndexedDB.** La foto se guarda primero y se sube después, con un indicador visible de cuántas quedan pendientes. Al ser solo Android, **Background Sync vacía la cola sola** cuando vuelve la señal, sin que el usuario abra nada.
3. **El camino principal no es el chat.** Una conversación con el agente cuesta varios viajes de red por comprobante. El flujo debe ser **foto → cola → confirmación cuando haya señal**, apoyado en los endpoints deterministas que ya existen (`/submissions/:id/confirm`), que no pasan por el modelo. El chat queda como ayuda para los casos dudosos, no como vía obligatoria. Esto además reduce a la mitad el costo de Gemini.
4. **Reintentos con backoff y timeouts largos del navegador al bot.** El bot ya los tiene hacia Sire; falta el tramo de subida.
5. **La sesión tiene que sobrevivir a días sin señal.** El JWT dura 60 minutos y el refresh 90 días: si el access token vence sin conexión, la app debe reintentar el refresh al recuperarla, no expulsar al usuario.

## Lo que se pierde frente a WhatsApp

Conviene decirlo con claridad: **en zonas rurales WhatsApp reintenta el envío solo**, y esa cola de reintentos es gratis, probada y funciona en cualquier teléfono. Es su mejor carta para este escenario.

La diferencia es que con Android la cola propia hace lo mismo —Background Sync cubre exactamente ese caso— y a cambio conservas el control del formato de la foto, de la compresión y de la confirmación. Si el parque fuera de iPhones, la balanza cambiaría: Safari no soporta Background Sync y toda la cola dependería de que el usuario reabra la app.

Los otros argumentos de WhatsApp —cero instalación, adopción masiva— pierden fuerza con 10 usuarios conocidos que reciben el enlace de su contador.

## WhatsApp como fase 2

No se descarta, se pospone. El 70 % del bot no depende del canal, así que añadirlo después cuesta unas 10 horas de capa de canal más el alta en Meta, y en ese momento no habrá un plazo encima. Tiene sentido reabrir la decisión si aparece alguno de estos tres casos:

- El cliente suma empresas o usuarios que no controla y la instalación se vuelve fricción real.
- Los usuarios rechazan la PWA y siguen mandando fotos por WhatsApp al contador por su cuenta.
- Se necesita avisar al usuario sin que abra la app (recordatorios, alertas de comprobante rechazado).

## Recomendación

**Construir la PWA, con Android como único objetivo y la cola offline como pieza central, y dejar WhatsApp para una fase posterior.** Es la única de las tres opciones que entra en dos semanas, la más barata en operación con 10 empresas, y la única que no obliga a tirar trabajo ya hecho ni a depender de un tercero que hoy no está configurado.

El riesgo de esta ruta no está en el canal: está en que las mismas dos semanas tienen que absorber el despliegue de Sire en Google Cloud, que sigue pendiente. Eso se trata en [cronograma.md](cronograma.md).
