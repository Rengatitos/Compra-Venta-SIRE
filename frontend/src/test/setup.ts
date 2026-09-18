import '@testing-library/jest-dom/vitest';

import * as matchers from 'vitest-axe/matchers';
import { beforeAll, expect } from 'vitest';

expect.extend(matchers);

/**
 * `jsdom` no implementa `showModal`/`close`, que es lo único que delegan en el
 * navegador tanto `Dialog` como el cajón de navegación. Se sustituyen por lo
 * mínimo para poder comprobar la estructura y el árbol accesible; el atrapado
 * de foco y el cierre con Escape se verifican en el navegador, no aquí.
 */
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function abrir(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function cerrar(this: HTMLDialogElement) {
    this.open = false;
  };
});
