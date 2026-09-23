import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';
import type { FormEvent } from 'react';

import { agregarUsuario, cambiarRol, listarUsuarios, quitarUsuario } from '@/api/usuarios';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { SelectField, TextField } from '@/components/ui/Field';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { RolUsuario, UsuarioAcceso } from '@/types/api';

import estilos from './GestionAccesos.module.css';
import { useEsAdmin } from './useEsAdmin';

const ROLES = [
  { valor: 'usuario', texto: 'Usuario (sin gestión de accesos)' },
  { valor: 'admin', texto: 'Administrador (puede dar accesos)' },
] as const;

function detalle(fallo: unknown): string {
  return fallo instanceof ApiError ? fallo.message : 'Error inesperado.';
}

/**
 * Quién puede entrar al panel. Solo la ven los administradores: para el resto
 * no se pinta nada (y el backend responde 403 de todas formas).
 *
 * Los administradores fijos (`GOOGLE_ALLOWED_EMAILS` del servidor) salen en la
 * lista pero sin acciones: se cambian en el servidor, no desde aquí.
 */
export function GestionAccesos() {
  const esAdmin = useEsAdmin();
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const idTitulo = useId();
  const [correo, setCorreo] = useState('');
  const [rol, setRol] = useState<RolUsuario>('usuario');

  const usuarios = useQuery({
    queryKey: ['usuarios'],
    queryFn: listarUsuarios,
    enabled: esAdmin,
  });

  const refrescar = () => cliente.invalidateQueries({ queryKey: ['usuarios'] });

  const agregar = useMutation({
    mutationFn: () => agregarUsuario(correo.trim(), rol),
    onSuccess: async (nuevo) => {
      mostrar({ tono: 'exito', titulo: `Acceso concedido a ${nuevo.email}` });
      setCorreo('');
      setRol('usuario');
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo dar acceso', detalle: detalle(fallo) }),
  });

  const cambiar = useMutation({
    mutationFn: (usuario: UsuarioAcceso) =>
      cambiarRol(usuario.email, usuario.rol === 'admin' ? 'usuario' : 'admin'),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Rol actualizado' });
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo cambiar el rol', detalle: detalle(fallo) }),
  });

  const quitar = useMutation({
    mutationFn: (email: string) => quitarUsuario(email),
    onSuccess: async (_vacio, email) => {
      mostrar({ tono: 'exito', titulo: `Acceso retirado a ${email}` });
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo quitar el acceso',
        detalle: detalle(fallo),
      }),
  });

  if (!esAdmin) return null;

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (correo.trim()) agregar.mutate();
  }

  const ocupado = cambiar.isPending || quitar.isPending;

  return (
    <section className={estilos.seccion} aria-labelledby={idTitulo}>
      <h2 className={estilos.titulo} id={idTitulo}>
        Accesos al panel
      </h2>
      <p className={layout.textoSecundario}>
        Correos de Google que pueden entrar. Los administradores también dan y quitan accesos;
        los usuarios solo trabajan con las empresas.
      </p>

      <form className={estilos.formulario} onSubmit={alEnviar}>
        <TextField
          etiqueta="Correo de Google"
          type="email"
          name="correo"
          value={correo}
          onChange={(evento) => setCorreo(evento.target.value)}
          autoComplete="off"
          required
        />
        <SelectField
          etiqueta="Rol"
          name="rol"
          value={rol}
          onChange={(evento) => setRol(evento.target.value as RolUsuario)}
          opciones={ROLES}
        />
        <div className={layout.filaFin}>
          <Button type="submit" variante="primario" pequeno cargando={agregar.isPending}>
            Dar acceso
          </Button>
        </div>
      </form>

      {usuarios.isPending ? <Skeleton lineas={2} etiqueta="Cargando los accesos" /> : null}
      {usuarios.isError ? (
        <ErrorState
          titulo="No se pudieron cargar los accesos"
          texto={detalle(usuarios.error)}
          accion={
            <Button pequeno onClick={() => void usuarios.refetch()}>
              Reintentar
            </Button>
          }
        />
      ) : null}

      {usuarios.data ? (
        <ul className={estilos.lista}>
          {usuarios.data.map((usuario) => (
            <li key={usuario.email} className={estilos.fila}>
              <span className={estilos.correo}>{usuario.email}</span>
              <span className={layout.fila}>
                <Badge tono={usuario.rol === 'admin' ? 'info' : 'neutro'}>
                  {usuario.rol === 'admin' ? 'Admin' : 'Usuario'}
                </Badge>
                {usuario.fijo ? <Badge tono="neutro">Fijo</Badge> : null}
              </span>
              {usuario.fijo ? null : (
                <span className={layout.fila}>
                  <Button
                    pequeno
                    variante="fantasma"
                    onClick={() => cambiar.mutate(usuario)}
                    disabled={ocupado}
                  >
                    {usuario.rol === 'admin' ? 'Hacer usuario' : 'Hacer admin'}
                  </Button>
                  <Button
                    pequeno
                    variante="peligro"
                    onClick={() => quitar.mutate(usuario.email)}
                    disabled={ocupado}
                    aria-label={`Quitar el acceso a ${usuario.email}`}
                  >
                    Quitar
                  </Button>
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
