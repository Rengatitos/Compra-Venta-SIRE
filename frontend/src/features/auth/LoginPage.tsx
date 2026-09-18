import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

import { Button } from '@/components/ui/Button';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import {
  cargarGoogleIdentity,
  hayClientId,
  inicializarGoogleIdentity,
  pintarBotonGoogle,
} from '@/lib/google';
import { ApiError } from '@/lib/http';
import { obtenerTema, suscribirTema } from '@/lib/theme';

import estilos from './Acceso.module.css';
import { useAuth } from './useAuth';

interface EstadoRuta {
  desde?: string;
}

type Estado = 'cargando' | 'listo' | 'sin-configurar' | 'no-disponible';

export function LoginPage() {
  useDocumentTitle('Iniciar sesión');

  const { iniciarSesionConGoogle } = useAuth();
  const navegar = useNavigate();
  const ubicacion = useLocation();
  const { mostrar } = useToast();

  const contenedor = useRef<HTMLDivElement>(null);
  const [estado, setEstado] = useState<Estado>('cargando');
  const [intento, setIntento] = useState(0);

  const alRecibirCredencial = useCallback(
    (idToken: string) => {
      void (async () => {
        try {
          await iniciarSesionConGoogle(idToken);
          const destino = (ubicacion.state as EstadoRuta | null)?.desde ?? '/';
          await navegar(destino, { replace: true });
        } catch (fallo) {
          // Por toast, como el resto del panel. El backend distingue «token
          // inválido» de «cuenta sin acceso»; su mensaje es más útil que
          // cualquier texto genérico de aquí.
          mostrar({
            tono: 'error',
            titulo: 'No se pudo iniciar sesión',
            detalle:
              fallo instanceof ApiError ? fallo.message : 'Inténtalo de nuevo en unos segundos.',
          });
        }
      })();
    },
    [iniciarSesionConGoogle, mostrar, navegar, ubicacion.state],
  );

  useEffect(() => {
    if (!hayClientId()) {
      // Mejor decirlo que pintar un botón que no va a responder.
      setEstado('sin-configurar');
      return;
    }

    let vigente = true;

    void cargarGoogleIdentity()
      .then(() => {
        if (!vigente || !contenedor.current) return;
        inicializarGoogleIdentity(alRecibirCredencial);
        pintarBotonGoogle(contenedor.current, obtenerTema());
        setEstado('listo');
      })
      .catch(() => {
        if (vigente) setEstado('no-disponible');
      });

    return () => {
      vigente = false;
    };
  }, [alRecibirCredencial, intento]);

  // El botón vive en un iframe de Google: no se puede estilar desde aquí, así
  // que la única forma de que no quede blanco sobre fondo oscuro es repintarlo.
  useEffect(() => {
    return suscribirTema((tema) => {
      if (estado === 'listo' && contenedor.current) pintarBotonGoogle(contenedor.current, tema);
    });
  }, [estado]);

  return (
    <main className={estilos.pagina}>
      <div className={estilos.tarjeta}>
        <div className={estilos.encabezado}>
          <p className={estilos.marca}>Sire · SUNAT</p>
          <ThemeToggle />
        </div>
        <h1 className={`${estilos.titulo} ${estilos.tituloEspaciado}`}>Iniciar sesión</h1>
        <p className={estilos.intro}>
          Entra con tu cuenta de Google. Desde dentro podrás cambiar de empresa sin volver a
          iniciar sesión.
        </p>

        {/* Contenedor del botón de Google. Sin `role` ni `tabIndex`: lo que va
            dentro es un iframe con su propio botón, y envolverlo en otro rol
            sería exactamente la violación de accesibilidad clásica. */}
        <div className={estilos.contenedorGoogle} ref={contenedor} />

        {estado === 'cargando' ? (
          <Skeleton lineas={1} etiqueta="Cargando el acceso con Google" />
        ) : null}

        {estado === 'sin-configurar' ? (
          <ErrorState
            titulo="Falta configurar el acceso con Google"
            texto="Define VITE_GOOGLE_CLIENT_ID en el frontend y vuelve a cargar la página."
          />
        ) : null}

        {estado === 'no-disponible' ? (
          <ErrorState
            titulo="No se pudo cargar el acceso con Google"
            texto="Puede ser la conexión o un bloqueador de contenido."
            accion={
              <Button
                variante="primario"
                onClick={() => {
                  setEstado('cargando');
                  setIntento((valor) => valor + 1);
                }}
              >
                Reintentar
              </Button>
            }
          />
        ) : null}
      </div>
    </main>
  );
}
