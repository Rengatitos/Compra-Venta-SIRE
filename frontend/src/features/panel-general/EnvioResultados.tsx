import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import { useState } from 'react';

import {
  enviarCorreoPrueba,
  guardarConfiguracionCorreo,
  obtenerConfiguracionCorreo,
} from '@/api/correos';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useAuth } from '@/features/auth/useAuth';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';

import estilos from './EnvioResultados.module.css';

/**
 * Lo único que un administrador necesita ver del correo: desde qué cuenta sale,
 * a quién llega y si está listo. El servidor SMTP y la plantilla quedan en
 * «Opciones avanzadas».
 */
export function EnvioResultados() {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const { correo } = useAuth();
  const [password, setPassword] = useState('');

  const config = useQuery({
    queryKey: ['configuracion-correo'],
    queryFn: obtenerConfiguracionCorreo,
  });

  const guardar = useMutation({
    mutationFn: () => guardarConfiguracionCorreo({ password }),
    onSuccess: (guardada) => {
      setPassword('');
      cliente.setQueryData(['configuracion-correo'], guardada);
      mostrar({ tono: 'exito', titulo: 'Contraseña guardada' });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo guardar',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const probar = useMutation({
    mutationFn: (destinatario: string) => enviarCorreoPrueba(destinatario),
    onSuccess: (respuesta) => mostrar({ tono: 'exito', titulo: respuesta.mensaje }),
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo enviar la prueba',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  if (config.isPending) return <Skeleton lineas={3} etiqueta="Cargando el envío de resultados" />;
  if (config.isError) {
    return (
      <ErrorState
        titulo="No se pudo cargar el envío de resultados"
        texto={config.error instanceof ApiError ? config.error.message : 'Error inesperado.'}
      />
    );
  }

  const datos = config.data;
  const remitente = datos.remitente_correo || datos.usuario;

  function alGuardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (password.trim()) guardar.mutate();
  }

  return (
    <Panel
      titulo="Envío de resultados"
      descripcion="Al terminar un procesamiento masivo, el ZIP con los archivos llega al correo de Google de quien lo pidió."
      acciones={
        <Badge tono={datos.configurado ? 'exito' : 'aviso'} conPunto>
          {datos.configurado ? 'Listo' : 'Falta un paso'}
        </Badge>
      }
    >
      <div className={estilos.flujo}>
        <div className={estilos.extremo}>
          <span className={estilos.etiqueta}>Se envía desde</span>
          <span className={estilos.correo}>{remitente || 'Sin remitente'}</span>
        </div>
        <span className={estilos.flecha} aria-hidden="true">
          →
        </span>
        <div className={estilos.extremo}>
          <span className={estilos.etiqueta}>Llega a</span>
          <span className={estilos.correo}>{correo ?? 'Tu correo de Google'}</span>
        </div>
      </div>

      {datos.password_configurada ? null : (
        <form className={estilos.paso} onSubmit={alGuardar} noValidate>
          <TextField
            etiqueta={`Contraseña de aplicación de ${remitente}`}
            name="password_aplicacion"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            ayuda="Gmail no acepta la contraseña normal de la cuenta. Créala en Cuenta de Google › Seguridad › Contraseñas de aplicación (pide la verificación en dos pasos)."
          />
          <Button
            type="submit"
            variante="primario"
            cargando={guardar.isPending}
            disabled={!password.trim()}
          >
            Guardar
          </Button>
        </form>
      )}

      {datos.configurado && correo ? (
        <div className={layout.fila}>
          <Button cargando={probar.isPending} onClick={() => probar.mutate(correo)}>
            Enviarme un correo de prueba
          </Button>
        </div>
      ) : null}
    </Panel>
  );
}
