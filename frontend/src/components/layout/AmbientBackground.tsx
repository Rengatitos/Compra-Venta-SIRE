import estilos from './AmbientBackground.module.css';

/**
 * Fondo ambiental puramente decorativo. `aria-hidden` porque no aporta
 * información: es la capa atmosférica que pide design.md, resuelta con CSS.
 */
export function AmbientBackground() {
  return (
    <div className={estilos.fondo} aria-hidden="true">
      <div className={estilos.reticula} />
    </div>
  );
}
