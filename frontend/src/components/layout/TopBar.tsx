import { Link } from 'react-router';

import { Button } from '@/components/ui/Button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { formatearRuc } from '@/lib/format';

import estilos from './TopBar.module.css';

interface Props {
  ruc: string;
  rubro: string | null;
  onSalir: () => void;
}

export function TopBar({ ruc, rubro, onSalir }: Props) {
  return (
    <div className={estilos.barra}>
      <Link className={estilos.marca} to="/">
        <span className={estilos.nombre}>SIRE</span>
        <span className={estilos.subtitulo}>Registro de compras electrónico</span>
      </Link>

      <div className={estilos.sesion}>
        <div className={estilos.datos}>
          <span className={estilos.ruc}>
            <span className="visually-hidden">RUC de la empresa: </span>
            {formatearRuc(ruc)}
          </span>
          <span className={estilos.rubro}>{rubro ?? 'Rubro no determinado'}</span>
        </div>
        <ThemeToggle />
        <Button variante="fantasma" pequeno onClick={onSalir}>
          Cerrar sesión
        </Button>
      </div>
    </div>
  );
}
