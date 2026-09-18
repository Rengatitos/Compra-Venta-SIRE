import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { ButtonLink } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

import estilos from './SelectorEmpresa.module.css';
import { ListaEmpresas } from './ListaEmpresas';
import { useEmpresas } from './useEmpresas';

/**
 * Cambio de empresa desde la barra lateral.
 *
 * Es un diálogo y no un `<select>` nativo por una razón concreta del proyecto:
 * el desplegable nativo lo pinta el sistema operativo, fuera del alcance de
 * `tokens.css`, así que en tema oscuro aparecería una lista clara del sistema —
 * justo la incoherencia de contraste que el resto del panel evita. Además cada
 * fila lleva dos niveles de texto (nombre y RUC monoespaciado + rubro) y un
 * `<option>` solo admite una línea.
 *
 * `Dialog` delega en el `<dialog>` nativo, así que el atrapado de foco, Escape y
 * la devolución del foco al disparador vienen dados.
 */
interface Props {
  /** A lo ancho de la columna: así lo quiere la barra lateral. */
  bloque?: boolean;
}

export function SelectorEmpresa({ bloque = false }: Props) {
  const { empresas, ruc, empresaActiva, cambiarEmpresa } = useEmpresas();
  const [abierto, setAbierto] = useState(false);

  const descripcion = empresaActiva?.nombre ?? empresaActiva?.rubro ?? 'Rubro no determinado';

  // Con una sola cuenta, un botón que abre un diálogo de una sola opción es
  // ruido: se muestra lo mismo como texto.
  if (empresas.length <= 1) {
    return (
      <div className={estilos.estatico}>
        <span className={estilos.ruc}>
          <span className="visually-hidden">Empresa activa: </span>
          {ruc}
        </span>
        <span className={estilos.descripcion}>{descripcion}</span>
      </div>
    );
  }

  return (
    <>
      {/* El nombre accesible va en `aria-label` y no en un `visually-hidden`
          suelto: el contenido visible son dos líneas sin separación, que se
          concatenarían en algo como «Empresa activa:20603391692Alfa». */}
      <Button
        variante="fantasma"
        pequeno
        bloque={bloque}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        aria-label={`Empresa activa: ${ruc ?? 'ninguna'}. Cambiar de empresa`}
        onClick={() => setAbierto(true)}
      >
        <span className={estilos.disparador}>
          <span className={estilos.ruc}>{ruc}</span>
          <span className={estilos.descripcion}>{descripcion}</span>
        </span>
      </Button>

      <Dialog
        abierto={abierto}
        titulo="Cambiar de empresa"
        texto="Se abrirá el panel de la empresa que elijas. No hace falta volver a iniciar sesión."
        onCerrar={() => setAbierto(false)}
        acciones={
          <>
            <ButtonLink a="/empresas/nueva" pequeno onClick={() => setAbierto(false)}>
              Registrar empresa
            </ButtonLink>
            <Button variante="fantasma" onClick={() => setAbierto(false)}>
              Cancelar
            </Button>
          </>
        }
      >
        <ListaEmpresas
          empresas={empresas}
          activo={ruc}
          onElegir={(elegido) => {
            setAbierto(false);
            cambiarEmpresa(elegido);
          }}
        />
      </Dialog>
    </>
  );
}
