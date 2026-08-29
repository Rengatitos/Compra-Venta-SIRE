# Frontend — Panel SIRE

SPA en React 19 + TypeScript que opera la API de [Sire](../README.md): alta y login de empresa,
periodos, sincronización de la propuesta de compras del SIRE, extracción de detalle del portal SOL
como job asíncrono, clasificación contable con IA, referencias PDF para el RAG, consulta / edición /
exportación de comprobantes y el dashboard de analítica.

## Arrancar

El backend debe estar corriendo en `http://127.0.0.1:9007` (ver el README raíz).

```bash
npm install --prefix frontend
```

```bash
npm run dev --prefix frontend
```

Queda en `http://localhost:5173`. En desarrollo, `/api` pasa por el proxy de Vite hacia el backend,
así que el navegador ve un solo origen y CORS no interviene. Para apuntar a otra API, copia
`.env.example` a `.env` y define `VITE_API_BASE_URL`.

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
periodo, desde donde se lanzan la extracción y el análisis), `/procesos`, `/referencias` y
`/ajustes`. La ficha de un comprobante no es una ruta: es un modal sobre el listado, direccionado
con `?comprobante=<serie>` para que el enlace se pueda compartir y «atrás» lo cierre.

Nadie llama a `fetch` fuera de `src/lib/http.ts`; hay una regla de ESLint que lo impide. Los hooks de
React Query viven junto a la pantalla que los usa, y `src/api/` solo contiene funciones puras.

## Decisiones que conviene conocer

**Sesión.** El token y el RUC van en `sessionStorage`, no en `localStorage`: el JWT del backend dura
`JWT_EXPIRE_HOURS` (2 h), así que persistirlo entre sesiones del navegador solo dejaría credenciales
muertas en disco. Un `401` limpia la sesión y devuelve al login con un aviso, porque caducar en
pantalla es el caso normal, no la excepción.

**Solo compras.** `libro=ventas` responde `501` en el backend (el RVIE no tiene cliente HTTP), así que
la opción existe en la interfaz pero está deshabilitada y explicada. La UI no deja provocar ese 501.

**`descartados` se muestra siempre.** La sincronización descarta las series que no empiezan por `F` o
`E` y las fechas fuera del periodo. Si solo se mostrara «se sincronizaron 12», nadie entendería
dónde quedaron las boletas.

**`sin_propuesta` no es un error.** Es el estado que escribe el backend cuando SUNAT no tiene
propuesta para el periodo, y tiene su propio badge.

**Jobs.** `POST …/detalle` responde `202` con un `job_id`. `JobsProvider` (en `features/jobs/`)
guarda los ids en `sessionStorage` y sondea cada uno con `useJobPolling`: `GET /jobs/{job_id}` cada
3 s, y **deja de consultar** al llegar a `completado` o `fallido`. El seguimiento es global, así que
el avance se ve en la campana de la barra superior desde cualquier pantalla y sobrevive a recargar.
El historial completo sale de `GET /jobs` y vive en `/procesos`.

**Sin pantalla de administración.** `GET /api/v1/empresas` exige el header `X-Admin-Token`. Meter ese
secreto en un bundle de navegador sería filtrarlo, así que ese endpoint se queda fuera del frontend.

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
  lo abrió.

Lo que conviene repetir a mano tras cambios de estilo: activar `prefers-reduced-motion: reduce` en
DevTools y comprobar que no queda ninguna animación, revisar el zoom al 200 %, y pasar axe por las
dos variantes de tema (no solo por la activa).
