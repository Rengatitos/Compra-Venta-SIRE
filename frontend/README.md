# Frontend — Panel SIRE

SPA en React 19 + TypeScript que opera la API de [Sire](../README.md): acceso con cuenta de Google,
alta de empresas y cambio de una a otra desde el panel,
periodos, sincronización de la propuesta de compras y ventas del SIRE, extracción de detalle y PDF
del portal SOL como job asíncrono, estado de la glosa por comprobante, detracciones, consulta /
edición / exportación de comprobantes, auditoría, reporte asociado, maestro de cuentas y el
dashboard de analítica.

## Arrancar

El backend debe estar corriendo en `http://127.0.0.1:9007`.

```bash
npm install --prefix frontend
```

```bash
npm run dev --prefix frontend
```

Queda en `http://localhost:5173`. En desarrollo, `/api` pasa por el proxy de Vite hacia el backend,
así que el navegador ve un solo origen y CORS no interviene. Copia `.env.example` a `.env` y define
`VITE_GOOGLE_CLIENT_ID` con el Client ID del cliente OAuth de Google —el mismo que usa el backend—,
y `VITE_API_BASE_URL` si quieres apuntar a otra API.

`http://localhost:5173` tiene que estar en los «Orígenes de JavaScript autorizados» de ese cliente en
Google Cloud; si no, el botón de Google falla en silencio. Sin `VITE_GOOGLE_CLIENT_ID`, `/login` lo
dice en pantalla en vez de pintar un botón que no responde.

## Scripts

| Script | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo con HMR y proxy al backend. |
| `npm run build` | `tsc -b` + build de producción en `dist/`. |
| `npm run typecheck` | Solo TypeScript, en modo estricto. |
| `npm run lint` | ESLint (incluye `jsx-a11y`) + Stylelint. |
| `npm test` | Vitest: unitarios y humo de accesibilidad con axe. |
| `npm run format` | Prettier. |

## Estructura

```
src/
  api/          una función por endpoint del backend, tipada
  types/        espejo de app/schemas (api.ts) y de app/domain (domain.ts)
  lib/          http.ts (único fetch), session.ts, format.ts, queryClient.ts
  styles/       tokens.css, reset.css, global.css, layouts.module.css
  components/   layout/ (armazón) y ui/ (kit de primitivos)
  features/     una carpeta por área funcional, igual que las rutas del backend
  hooks/        useJobPolling, useToast, useDocumentTitle, usePrefersReducedMotion
```

Las rutas autenticadas son `/` (dashboard), `/periodos`, `/periodos/:periodo` (comprobantes del
periodo, con el conmutador compras/ventas, desde donde se lanzan la extracción de detalle, las
descargas y las detracciones), `/periodos/:periodo/auditoria`, `/periodos/:periodo/reporte`,
`/procesos`, `/plan-cuentas` y `/ajustes`. La ficha de un comprobante no es una ruta: es un modal
sobre el listado, direccionado con `?comprobante=<serie>` para que el enlace se pueda compartir y
«atrás» lo cierre.

En el listado, la columna **Estado glosa** (`features/comprobantes/estadoGlosa.ts`) muestra con una
insignia si el comprobante tiene glosa, no la tiene, está en evaluación o pendiente de consultar,
y la tarjeta «Con glosa» resume los cuatro conteos de todo el libro (`GET …/cobertura-sunat`). La
ficha añade la observación y la leyenda de SUNAT junto a la descripción editable.

Nadie llama a `fetch` fuera de `src/lib/http.ts`; hay una regla de ESLint que lo impide. Los hooks de
React Query viven junto a la pantalla que los usa, y `src/api/` solo contiene funciones puras.

## Decisiones que conviene conocer

**Sesión.** El JWT identifica a una **persona** (el correo con el que entró por Google), no a una
empresa. Va en `sessionStorage` y no en `localStorage`: dura `JWT_EXPIRE_HOURS` (2 h), así que
persistirlo entre sesiones del navegador solo dejaría credenciales muertas en disco. Un `401` limpia
la sesión y devuelve al login con un aviso, porque caducar en pantalla es el caso normal.

La **empresa activa** se guarda dentro del mismo objeto de sesión, lo que la ata al correo por
construcción: si en la misma pestaña entra otra persona, no hereda la cuenta que dejó elegida la
anterior. Una sesión con la forma anterior (`{token, ruc}`, sin correo) no valida al leerse y manda a
`/login`: su JWT identificaba a una empresa y el backend ya no lo acepta.

**Multiempresa.** `useRuc()` sigue siendo el único punto del que las pantallas obtienen el RUC, pero
ahora sale de `features/empresas` y no de la sesión. `EmpresaGate` se monta entre `ProtectedRoute`
(que exige sesión) y `AppShell` (que exige empresa activa): carga `GET /empresas`, entra directo si
solo hay una, pide elegir si hay varias y ofrece el alta incrustada si no hay ninguna — ese último
estado antes era inalcanzable, porque se entraba con las credenciales de una empresa que por
definición existía.

**Fuera del armazón.** `/login`, las pantallas del gate y `/empresas/nueva` comparten el componente
`Marco` y no se montan dentro de `AppShell`. La razón es la misma en los tres casos: `AppShell` da
por hecha una empresa activa, su barra lateral la anuncia y marca además la sección en curso.
Una pantalla anterior a esa elección no tiene empresa, y el alta habla de una distinta de la activa,
así que dentro del armazón la barra contradice al contenido y la navegación se queda sin ninguna
sección marcada. Se llega al alta desde el selector de cuentas y se vuelve con «Volver al panel».

**La barra lateral.** `SideNav` reúne todo lo que no es contenido: la marca, la empresa activa, la
campana de los trabajos, las secciones y la zona de cuenta (tema, cierre de sesión y quién está
dentro). **En escritorio no hay barra superior**: con la campana dentro, una banda arriba solo
dejaba una franja vacía y un escalón contra la tarjeta lateral, que empieza 12 px más abajo.
`TopBar` reaparece por debajo de 60rem, que es donde hace falta un sitio para el botón del cajón y
para la campana; la de la barra se oculta ahí para no duplicarla.

Que se quede fija al desplazar condiciona la maqueta de `AppShell`: un elemento `sticky` no puede
salir de su bloque contenedor, y el de un ítem de rejilla es su área, así que una cabecera metida
en una fila `auto` no tendría recorrido —no lo tenía—. Por eso la barra ocupa una columna propia de
alto completo y el contenido y el pie viven en una segunda columna de flujo normal. La barra lleva
`z-index` propio porque `position: sticky` crea contexto de apilado: sin él, la columna de
contenido taparía el panel de notificaciones, que se despliega desde el encabezado hacia la
derecha (`alineacion="inicio"`, porque alineado al final se saldría de una columna de 16rem).

«Periodos» es el único ítem con segundo nivel, y no es una lista fija: son las tres pantallas del
periodo que se está mirando (`/periodos/:periodo`, `…/auditoria` y `…/reporte`), que antes solo se
alcanzaban desde enlaces dentro del contenido. El grupo se abre solo al entrar en la sección y se
puede cerrar a mano; fuera de un periodo no hay ni chevron. El padre lleva `end` a propósito: sin
él, `/periodos` y el hijo activo reclamarían `aria-current="page"` a la vez.

Por debajo de 60rem la barra sale de la maqueta y se sirve como cajón desde el botón de la
cabecera. Es un `<dialog>` nativo por el mismo motivo que el selector de cuentas: el atrapado de
foco, Escape, la devolución del foco al disparador y la capa superior los pone el navegador.

Cambiar de empresa **no vacía el caché de React Query**. Todas las claves llevan ya el RUC
(`['comprobantes', ruc, …]`, `['periodos', ruc]`, `['jobs', ruc, …]`…), así que al cambiarlo ninguna
consulta encuentra caché y cada pantalla pinta su `Skeleton`; un `clear()` además tiraría la lista de
empresas y perdería la caché de la cuenta anterior, que es lo que hace instantáneo volver a ella. Lo
único que sí se hace es navegar a `/`: `/periodos/202607` puede no existir en la empresa nueva.
`clear()` se reserva para cerrar sesión.

**Google Identity Services sin dependencias.** Se carga el script oficial a mano desde
`src/lib/google.ts`, único punto que toca `window.google` (mismo criterio que `http.ts` con `fetch`).
`@react-oauth/google` es un envoltorio del mismo script: no evita el iframe, ni el `client_id`, ni
registrar el origen en Google Cloud. Encapsularlo es además lo que permite simularlo entero en los
tests, porque en jsdom un `<script src>` externo nunca se ejecuta. Los tipos están en
`src/types/google.d.ts` y no en `@types/google.one-tap`: `tsconfig.app.json` fija el array `types`,
así que un paquete de tipos globales no se cargaría sin tocarlo.

El Client ID viaja en el bundle y no pasa nada: no es un secreto, lo que protege el acceso son los
orígenes autorizados de Google Cloud y la lista de correos del backend.

**Dos libros.** Compras (RCE) y ventas (RVIE) comparten pantalla y se alternan con el control
segmentado de la cabecera; al crear un periodo se sincronizan ambos en serie. La barra de progreso de
un job sigue al libro seleccionado, y el job del otro libro se anuncia aparte.

**`descartados` se muestra siempre.** La sincronización descarta las series que no empiezan por `F` o
`E` y las fechas fuera del periodo. Si solo se mostrara «se sincronizaron 12», nadie entendería
dónde quedaron las boletas.

**`sin_propuesta` no es un error.** Es el estado que escribe el backend cuando SUNAT no tiene
propuesta para el periodo, y tiene su propio badge.

**Jobs.** `POST …/detalle` responde `202` con un `job_id`. `JobsProvider` (en `features/jobs/`)
guarda los ids en `sessionStorage` y sondea cada uno con `useJobPolling`: `GET /jobs/{job_id}` cada
3 s, y **deja de consultar** al llegar a `completado` o `fallido`. El seguimiento es global, así que
el avance se ve en la campana de la barra lateral desde cualquier pantalla y sobrevive a recargar.
El historial completo sale de `GET /jobs` y vive en `/procesos`.

**Selector de cuentas.** `GET /api/v1/empresas` ya no exige el token de administrador, así que la
lista de empresas vive en la barra lateral. Es un diálogo con filtro y no un `<select>` nativo: el
desplegable nativo lo pinta el sistema operativo, fuera del alcance de `tokens.css`, y en tema oscuro
aparecería una lista clara del sistema; además cada fila lleva dos niveles de texto y un `<option>`
solo admite una línea. Tampoco es un listbox ARIA a medida, donde el foco virtual y el `tabindex`
rotativo se rompen con facilidad y **axe no lo detecta**: los tests darían verde con algo inservible
por teclado. Con `Dialog` sobre el `<dialog>` nativo, las opciones son `<button>` de verdad.

## Diseño

`src/styles/tokens.css` es la única fuente de color, tipografía, espaciado y radios, basada en el
frontmatter de [design.md](../design.md).

### Tema claro y oscuro

**El modo claro es el predeterminado.** El oscuro (el de `design.md`) se activa con
`data-theme="dark"` en el elemento raíz, y el icono de sol/luna de la cabecera —presente también en
las pantallas de acceso— alterna entre ambos. La preferencia se guarda en `localStorage`, no en
`sessionStorage`: a diferencia del token de sesión es una comodidad del dispositivo que conviene
recordar entre visitas.

Un script en línea de `index.html` aplica el atributo antes del primer pintado, así que quien haya
elegido el oscuro no ve un destello claro al cargar. No se sigue `prefers-color-scheme`: el arranque
en claro es un requisito del producto, y solo se respeta la elección explícita del usuario.

En los tokens únicamente se redefinen los colores; tipografía, espaciado, radios y motion son
comunes, de modo que ningún componente necesita saber en qué tema está. Dos desviaciones respecto de
`design.md`, ambas por contraste, explicadas en la cabecera del archivo:

- `surface: #94A3B8` con texto blanco da 2.56:1 y no cumple AA. En el tema oscuro ese color pasa a
  acento y texto secundario sobre fondo oscuro (7:1 en el peor caso medido) y las superficies son
  negros elevados, que es además lo que muestra la referencia visual.
- En el tema claro esa gama tampoco sirve (#94A3B8 sobre blanco da 2.56:1): los grises de texto
  bajan a slate-600/700 y la paleta de gráficos se oscurece para mantener 3:1 como objeto gráfico.
- Los colores de estado del tema claro usan la familia 800 de Tailwind, no la 700: medidos contra su
  propio fondo teñido sobre `--color-surface-3` —el peor caso, una insignia dentro de una tabla— el
  verde y el ámbar de la 700 se quedaban en 3.9:1. Cada token lleva su ratio anotado al lado.

**Ninguna propiedad de color está en transición.** Sus valores vienen de tokens que se sustituyen de
golpe al cambiar de tema, y una propiedad de color en transición puede quedarse congelada en el color
del tema anterior — el botón primario acababa con texto casi negro sobre fondo casi negro. Se
transicionan solo `transform`, `box-shadow` y el ancho de la barra de progreso, que no dependen del
tema. Si añades una transición, que no sea de color.

Estilos en CSS Modules: cada selector es una sola clase, no hay `!important` (Stylelint lo prohíbe) ni
selectores de más de tres niveles, y no hay `overflow-x: hidden` global — cada tabla ancha tiene su
propia región desplazable, enfocable con el teclado.

## Accesibilidad

- `<html lang="es">`, un `<h1>` por pantalla, landmarks `header` / `nav` / `main` / `footer` y enlace
  «Saltar al contenido» como primer elemento enfocable.
- Cada gráfico va acompañado de la misma serie como `<table>` real; el SVG queda `aria-hidden` e
  `inert`, y un botón permite mostrar la tabla también en pantalla.
- Formularios con `<label>` real, `aria-describedby` para ayuda y error, `aria-invalid` y
  `role="alert"`. El placeholder nunca hace de etiqueta.
- Diálogos sobre `<dialog>` nativo: el atrapado de foco, el cierre con Escape y la devolución del
  foco los aporta el navegador.
- Progreso con `<progress>` nativo y mensajes en `aria-live`.
- Animaciones solo de `transform` y `opacity`, dentro de
  `@media (prefers-reduced-motion: no-preference)`: el estado sin movimiento es el predeterminado.

Verificado en el navegador con axe-core: **0 violaciones WCAG 2.1 A/AA en las rutas × los 2
temas**. Además:

- Los nodos que axe no puede evaluar (texto sobre el gradiente ambiental) se comprobaron a mano
  contra el punto más oscuro del fondo: 5.66:1 en claro y 5.91:1 en oscuro, el peor par de texto.
- Las cuatro series de gráfico superan 3:1 contra la superficie del panel en ambos temas (3.52:1 el
  peor caso, en claro).
- Sin desbordamiento horizontal del `body` a 375 px: la tabla ancha se desplaza dentro de su propia
  región, enfocable y con nombre accesible.
- El diálogo modal abre moviendo el foco dentro, cierra con `cancel` y devuelve el foco al botón que
  lo abrió. Vale también para el selector de cuentas, que se apoya en el mismo componente.

**El botón de Google es la excepción del sistema de diseño.** Lo renderiza Google dentro de un
iframe de otro origen, así que axe no puede entrar —ni en Vitest ni en el navegador— y su apariencia
no se puede tocar desde aquí. Su nombre accesible, su contraste y su anillo de foco son cosa de
Google; lo que sí se verifica es la página alrededor, y el `<div>` que lo contiene va sin `role` ni
`tabIndex` (envolverlo en un `role="button"` sería la violación clásica). Lo único que hace el
proyecto es repintarlo al cambiar de tema, porque si no queda blanco sobre fondo oscuro.

Lo que conviene repetir a mano tras cambios de estilo: activar `prefers-reduced-motion: reduce` en
DevTools y comprobar que no queda ninguna animación, revisar el zoom al 200 %, y pasar axe por las
dos variantes de tema (no solo por la activa) en `/login`, en la pantalla de elección de empresa y
con el selector de cuentas abierto.
