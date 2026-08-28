import { Button } from './Button';
import estilos from './Pagination.module.css';

interface Props {
  pagina: number;
  /** Se asume que hay página siguiente si la actual vino llena. */
  haySiguiente: boolean;
  onCambiar: (pagina: number) => void;
}

export function Pagination({ pagina, haySiguiente, onCambiar }: Props) {
  return (
    <nav className={estilos.navegacion} aria-label="Paginación de comprobantes">
      <Button
        pequeno
        onClick={() => onCambiar(pagina - 1)}
        disabled={pagina <= 1}
      >
        Anterior
      </Button>
      <p className={estilos.indicador} aria-live="polite">
        Página {pagina}
      </p>
      <Button pequeno onClick={() => onCambiar(pagina + 1)} disabled={!haySiguiente}>
        Siguiente
      </Button>
    </nav>
  );
}
