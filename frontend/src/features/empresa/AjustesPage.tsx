import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import {
  actualizarEmpresa,
  eliminarEmpresa,
  obtenerCredencialesSunat,
  obtenerEmpresa,
} from '@/api/empresas';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useEmpresas } from '@/features/empresas/useEmpresas';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';
import { guardarEmpresaActiva } from '@/lib/session';
import layout from '@/styles/layouts.module.css';

import { ActividadesEmpresaPanel } from './ActividadesEmpresaPanel';
import { VinculacionBotPanel } from './VinculacionBotPanel';

export function AjustesPage() {
  useDocumentTitle('Ajustes de la empresa');

  const ruc = useRuc();
  const { recargar } = useEmpresas();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [editarSol, setEditarSol] = useState(false);
  const [usuario, setUsuario] = useState('');
  const [password, setPassword] = useState('');
  const [confirmarBorrado, setConfirmarBorrado] = useState(false);

  const empresa = useQuery({
    queryKey: ['empresa', ruc],
    queryFn: () => obtenerEmpresa(ruc),
  });

  function cerrarEdicionSol() {
    setEditarSol(false);
    setUsuario('');
    setPassword('');
  }

  // Solo usuario y clave SOL: el Client ID y el Secret los trae «Obtener de
  // SUNAT» entrando con ellos, así que no se escriben a mano.
  const guardarSol = useMutation({
    mutationFn: () => actualizarEmpresa(ruc, { usuario, password }),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Usuario y clave SOL actualizados' });
      cerrarEdicionSol();
      await cliente.invalidateQueries({ queryKey: ['empresa', ruc] });
      recargar();
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudieron guardar los cambios',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const traerCredenciales = useMutation({
    mutationFn: () => obtenerCredencialesSunat(ruc),
    onSuccess: async (resultado) => {
      mostrar({
        tono: resultado.token_valido ? 'exito' : 'neutro',
        titulo: `Credenciales de API SUNAT: ${resultado.aplicacion}`,
        detalle: resultado.mensaje,
      });
      await cliente.invalidateQueries({ queryKey: ['empresa', ruc] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudieron traer las credenciales de SUNAT',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const borrar = useMutation({
    mutationFn: () => eliminarEmpresa(ruc),
    onSuccess: () => {
      setConfirmarBorrado(false);
      mostrar({ tono: 'exito', titulo: 'La empresa se eliminó del sistema' });
      // La sesión es de una persona, no de la empresa: se suelta la empresa
      // activa y el gate vuelve a pedir cuál —o muestra el estado vacío si era
      // la última.
      guardarEmpresaActiva(null);
      recargar();
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo eliminar la empresa',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  function alGuardarSol(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    guardarSol.mutate();
  }

  const datos = empresa.data;

  return (
    <>
      <PageHeader
        titulo="Ajustes de la empresa"
        descripcion="Conexión con Apaclla Bot, acceso a SUNAT y actividades económicas."
      />

      <div className={layout.pilaAmplia}>
        <VinculacionBotPanel ruc={ruc} />

        <Panel
          titulo="Acceso a SUNAT"
          descripcion="Sire entra a SOL con el usuario y la clave guardados y trae solo las credenciales de la API SIRE. Si la empresa no tiene una aplicación registrada, la crea. Tarda cerca de un minuto."
          acciones={
            <Button
              variante="primario"
              onClick={() => traerCredenciales.mutate()}
              cargando={traerCredenciales.isPending}
            >
              {traerCredenciales.isPending ? 'Entrando a SOL…' : 'Obtener de SUNAT'}
            </Button>
          }
        >
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
                <dd className={layout.descripcion}>{datos.rubro ?? 'No determinado'}</dd>
              </div>
              <div>
                <dt className={layout.termino}>Registrada</dt>
                <dd className={layout.descripcion}>
                  {formatearFechaHora(datos.fecha_creacion)}
                  {datos.registro ? ` · ${datos.registro.por}` : ''}
                </dd>
              </div>
            </dl>
          ) : null}

          <div className={layout.fila}>
            <Button pequeno variante="fantasma" onClick={() => setEditarSol(true)}>
              Cambiar usuario y clave SOL
            </Button>
          </div>
        </Panel>

        <ActividadesEmpresaPanel ruc={ruc} empresa={datos} />

        <Panel
          titulo="Eliminar la empresa"
          descripcion="Borra en cascada los comprobantes, los periodos y la propia empresa."
        >
          <div className={layout.filaFin}>
            <Button variante="peligro" onClick={() => setConfirmarBorrado(true)}>
              Eliminar empresa
            </Button>
          </div>
        </Panel>
      </div>

      <Dialog
        abierto={editarSol}
        titulo="Cambiar usuario y clave SOL"
        texto="Úsalo solo si cambiaron en SUNAT. Deja un campo vacío para conservar el actual."
        onCerrar={cerrarEdicionSol}
        acciones={
          <>
            <Button variante="fantasma" onClick={cerrarEdicionSol}>
              Cancelar
            </Button>
            <Button
              type="submit"
              form="form-credenciales-sol"
              variante="primario"
              cargando={guardarSol.isPending}
              disabled={!usuario.trim() && !password}
            >
              Guardar
            </Button>
          </>
        }
      >
        <form id="form-credenciales-sol" className={layout.pila} onSubmit={alGuardarSol}>
          <TextField
            etiqueta="Usuario SOL"
            name="usuario"
            value={usuario}
            onChange={(evento) => setUsuario(evento.target.value)}
            autoComplete="off"
            placeholder={datos?.usuario}
          />
          <TextField
            etiqueta="Clave SOL"
            name="password"
            type="password"
            value={password}
            onChange={(evento) => setPassword(evento.target.value)}
            autoComplete="new-password"
          />
        </form>
      </Dialog>

      <Dialog
        abierto={confirmarBorrado}
        titulo="¿Eliminar la empresa y todos sus datos?"
        texto="Se borrarán comprobantes y periodos. Esta acción no se puede deshacer."
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
