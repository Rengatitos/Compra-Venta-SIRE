import type { ReactNode } from 'react';

import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

import estilos from './Marco.module.css';

interface Props {
  titulo: string;
  intro?: ReactNode;
  children: ReactNode;
  /** Acción de salida al pie: cerrar sesión, volver al panel… */
  pie?: ReactNode;
  /** Opciones junto al selector de tema, arriba a la derecha. */
  acciones?: ReactNode;
  /** `amplio` para pantallas con tablas, como el resultado de una carga. */
  ancho?: 'normal' | 'amplio';
  /**
   * El `<h1>` sigue existiendo para lectores de pantalla, pero no se ve: para
   * pantallas cuyo contenido ya trae sus propios títulos (p. ej. con pestañas).
   */
  tituloOculto?: boolean;
}

/**
 * Marco de las pantallas que van **fuera** del panel.
 *
 * Todo lo que vive dentro de `AppShell` —la barra con la empresa activa, la
 * navegación lateral, el seguimiento de trabajos— da por hecho que hay una
 * empresa elegida. Estas pantallas o son anteriores a esa elección (el gate) o
 * hablan de otra empresa distinta de la activa (el alta), así que meterlas en
 * el armazón deja la barra contradiciendo al contenido y la navegación sin
 * ninguna sección marcada.
 */
export function Marco({
  titulo,
  intro,
  children,
  pie,
  acciones,
  ancho = 'normal',
  tituloOculto = false,
}: Props) {
  useDocumentTitle(titulo);

  return (
    <main className={estilos.pagina}>
      <div
        className={
          ancho === 'amplio' ? `${estilos.tarjeta} ${estilos.amplia}` : estilos.tarjeta
        }
      >
        <div className={estilos.encabezado}>
          <p className={estilos.marca}>Sire · SUNAT</p>
          <div className={estilos.herramientas}>
            {acciones}
            <ThemeToggle />
          </div>
        </div>
        <h1 className={tituloOculto ? 'visually-hidden' : estilos.titulo}>{titulo}</h1>
        {intro ? <p className={estilos.intro}>{intro}</p> : null}
        {children}
        {pie ? <p className={estilos.pie}>{pie}</p> : null}
      </div>
    </main>
  );
}
