import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import {
  actualizarEmpresa,
  eliminarEmpresa,
  obtenerEmpresa,
  renovarTokenSunat,
} from '@/api/empresas';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useAuth, useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';

export function AjustesPage() {
  useDocumentTitle('Ajustes de la empresa');

  const ruc = useRuc();
  const { salir } = useAuth();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [usuario, setUsuario] = useState('');
  const [password, setPassword] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [confirmarBorrado, setConfirmarBorrado] = useState(false);

  const empresa = useQuery({
    queryKey: ['empresa', ruc],
    queryFn: () => obtenerEmpresa(ruc),
  });

  const guardar = useMutation({
    mutationFn: () =>
      actualizarEmpresa(ruc, {
        usuario,
        password,
        sunat_client_id: clientId,
        sunat_client_secret: clientSecret,
      }),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Datos de la empresa actualizados' });
      setPassword('');
      setClientSecret('');
      await cliente.invalidateQueries({ queryKey: ['empresa', ruc] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudieron guardar los cambios',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const renovar = useMutation({
    mutationFn: () => renovarTokenSunat(ruc),
    onSuccess: (respuesta) => {
      mostrar({
        tono: 'exito',
        titulo: 'Token de SUNAT renovado',
        detalle: respuesta.mensaje ?? undefined,
      });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo renovar el token de SUNAT',
        detalle:
          fallo instanceof ApiError
            ? fallo.message
            : 'Revisa el Client ID y el Client Secret configurados.',
      });
    },
  });

  const borrar = useMutation({
    mutationFn: () => eliminarEmpresa(ruc),
    onSuccess: () => {
      setConfirmarBorrado(false);
      mostrar({ tono: 'exito', titulo: 'La empresa se eliminó del sistema' });
      salir();
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo eliminar la empresa',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  function alGuardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    guardar.mutate();
  }

  const datos = empresa.data;

  return (
    <>
      <PageHeader
        titulo="Ajustes de la empresa"
        descripcion="Credenciales SOL, credenciales de la API SIRE y ciclo de vida de la cuenta."
      />

      <div className={layout.pilaAmplia}>
        <Panel titulo="Datos actuales">
          {empresa.isPending ? <Skeleton lineas={3} etiqueta="Cargando la empresa" /> : null}

          {empresa.isError ? (
            <ErrorState
              titulo="No se pudieron cargar los datos de la empresa"
              texto={
                empresa.error instanceof ApiError ? empresa.error.message : 'Error inesperado.'
              }
              accion={
                <Button pequeno onClick={() => void empresa.refetch()}>
                  Reintentar
                </Button>
              }
            />
          ) : null}

          {datos ? (
            <dl className={layout.definiciones}>
              <div>
                <dt className={layout.termino}>RUC</dt>
                <dd className={layout.descripcion}>{datos.ruc}</dd>
              </div>
              <div>
                <dt className={layout.termino}>Usuario SOL</dt>
                <dd className={layout.descripcion}>{datos.usuario}</dd>
              </div>
              <div>
                <dt className={layout.termino}>Rubro</dt>
                <dd className={layout.descripcion}>
                  {datos.rubro ?? 'No determinado (depende del CIIU del token de SUNAT)'}
                </dd>
              </div>
              <div>
                <dt className={layout.termino}>Alta</dt>
                <dd className={layout.descripcion}>{datos.fecha_creacion ?? '—'}</dd>
              </div>
            </dl>
          ) : null}
        </Panel>

        <Panel
          titulo="Actualizar credenciales"
          descripcion="Solo se envían los campos que rellenes. Dejar uno vacío significa «no lo toques», nunca «bórralo»."
        >
          <form className={layout.pila} onSubmit={alGuardar}>
            <div className={layout.rejillaFormulario}>
              <TextField
                etiqueta="Usuario SOL"
                name="usuario"
                value={usuario}
                onChange={(evento) => setUsuario(evento.target.value)}
                autoComplete="off"
                ayuda={datos ? `Actual: ${datos.usuario}` : undefined}
              />
              <TextField
                etiqueta="Nueva contraseña SOL"
                name="password"
                type="password"
                value={password}
                onChange={(evento) => setPassword(evento.target.value)}
                autoComplete="new-password"
                ayuda="Se vuelve a cifrar al guardarla."
              />
              <TextField
                etiqueta="Client ID de SUNAT"
                name="sunat_client_id"
                value={clientId}
                onChange={(evento) => setClientId(evento.target.value)}
                autoComplete="off"
                mono
              />
              <TextField
                etiqueta="Client Secret de SUNAT"
                name="sunat_client_secret"
                type="password"
                value={clientSecret}
                onChange={(evento) => setClientSecret(evento.target.value)}
                autoComplete="off"
              />
            </div>
            <div className={layout.filaFin}>
              <Button type="submit" variante="primario" cargando={guardar.isPending}>
                Guardar cambios
              </Button>
            </div>
          </form>
        </Panel>

        <Panel
          titulo="Token de la API SIRE"
          descripcion="Fuerza un token nuevo con las credenciales de cliente de la empresa, o con las globales de respaldo si no tiene propias. El rubro que usa la IA se deduce de este token."
        >
          <div className={layout.filaFin}>
            <Button onClick={() => renovar.mutate()} cargando={renovar.isPending}>
              Renovar token de SUNAT
            </Button>
          </div>
        </Panel>

        <Panel
          titulo="Eliminar la empresa"
          descripcion="Borra en cascada los comprobantes, los periodos, las referencias indexadas y la propia empresa."
        >
          <div className={layout.filaFin}>
            <Button variante="peligro" onClick={() => setConfirmarBorrado(true)}>
              Eliminar empresa
            </Button>
          </div>
        </Panel>
      </div>

      <Dialog
        abierto={confirmarBorrado}
        titulo="¿Eliminar la empresa y todos sus datos?"
        texto="Se borrarán comprobantes, periodos y referencias vectoriales. Esta acción no se puede deshacer y cerrará tu sesión."
        onCerrar={() => setConfirmarBorrado(false)}
        acciones={
          <>
            <Button variante="fantasma" onClick={() => setConfirmarBorrado(false)}>
              Cancelar
            </Button>
            <Button
              variante="peligro"
              cargando={borrar.isPending}
              onClick={() => borrar.mutate()}
            >
              Sí, eliminar todo
            </Button>
          </>
        }
      />
    </>
  );
}
