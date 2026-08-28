/**
 * `vitest-axe` sigue declarando su matcher en el namespace global `Vi`, que
 * Vitest 3 ya no usa. Se añade aquí la ampliación del módulo actual.
 */
import 'vitest';

declare module 'vitest' {
  interface Assertion {
    toHaveNoViolations(): void;
  }
  interface AsymmetricMatchersContaining {
    toHaveNoViolations(): void;
  }
}
