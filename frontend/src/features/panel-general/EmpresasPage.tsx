import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { eliminarEmpresa } from '@/api/empresas';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { type Columna, DataTable } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { presentarTipoJob } from '@/features/jobs/estadoJob';
import { useEsAdmin } from '@/features/usuarios/useEsAdmin';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearEntero, formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';
import { guardarEmpresaActiva } from '@/lib/session';
import layout from '@/styles/layouts.module.css';
import type { ResumenEmpresa } from '@/types/api';

import { CorregirEmpresa } from './CorregirEmpresa';
import estilos from './EmpresasPage.module.css';
import { useSeleccion } from './seleccionContext';
import { useResumenEmpresas } from './useResumenEmpresas';

/**
 * Todas las empresas de un vistazo: cuántas hay, sus periodos, cuándo se bajó
 * por última vez su SIRE y su último proceso. Es la pantalla de entrada; aquí
 * se marcan las empresas que luego se lanzan desde «Procesamiento masivo».
 *
 * Una empresa sin credenciales del API SUNAT no sirve para nada: se ve apagada,
 * no se abre ni se procesa, y ofrece leer el motivo y corregir sus datos SOL.
 */
export function EmpresasPage() {
  useDocumentTitle('Empresas');
  const navegar = useNavigate();
  const esAdmin = useEsAdmin();
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const [filtro, setFiltro] = useState('');
  const { seleccion, setSeleccion } = useSeleccion();
  const { resumen, empresas } = useResumenEmpresas();
  // Diálogos de una fila: por qué requiere corrección, corregirla o borrarla.
  const [motivo, setMotivo] = useState<ResumenEmpresa | null>(null);
  const [corregir, setCorregir] = useState<ResumenEmpresa | null>(null);
  const [borrar, setBorrar] = useState<ResumenEmpresa | null>(null);

  const visibles = filtrar(empresas, filtro);
  // Solo las que están listas se pueden abrir o mandar a procesar.
  const seleccionables = visibles.filter((e) => e.estado_alta === 'lista');

  function entrar(ruc: string, destino = '/dashboard') {
    guardarEmpresaActiva(ruc);
    void navegar(destino);
  }

  const eliminar = useMutation({
    mutationFn: (ruc: string) => eliminarEmpresa(ruc),
    onSuccess: async (_respuesta, ruc) => {
      const nombre = borrar?.nombre ?? ruc;
      setBorrar(null);
      if (seleccion.has(ruc)) {
        const nueva = new Set(seleccion);
        nueva.delete(ruc);
        setSeleccion(nueva);
      }
      mostrar({ tono: 'exito', titulo: `Se eliminó ${nombre}` });
      await cliente.invalidateQueries({ queryKey: ['resumen-empresas'] });
      await cliente.invalidateQueries({ queryKey: ['empresas'] });
    },
    onError: (fallo) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo eliminar la empresa',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      }),
  });

  // La selección sobrevive al filtro: filtrar sirve para encontrar y marcar,
  // no para desmarcar lo que ya se eligió.
  const marcadas = empresas.filter(
    (e) => e.estado_alta === 'lista' && seleccion.has(e.ruc),
  ).length;
  const visiblesMarcadas = seleccionables.filter((e) => seleccion.has(e.ruc)).length;

  function alternar(ruc: string) {
    const nueva = new Set(seleccion);
    if (nueva.has(ruc)) nueva.delete(ruc);
    else nueva.add(ruc);
    setSeleccion(nueva);
  }

  function alternarVisibles() {
    const nueva = new Set(seleccion);
    const todasVisibles =
      seleccionables.length > 0 && visiblesMarcadas === seleccionables.length;
    for (const e of seleccionables) {
      if (todasVisibles) nueva.delete(e.ruc);
      else nueva.add(e.ruc);
    }
    setSeleccion(nueva);
  }

  const columnas: readonly Columna<ResumenEmpresa>[] = [
    {
      clave: 'seleccion',
      cabecera: 'Procesar',
      render: (fila) => (
        // La casilla es una rejilla: `text-align` no la centra.
        <div className={estilos.centro}>
          <Checkbox
            etiqueta={`Procesar ${fila.nombre ?? fila.ruc}`}
            etiquetaOculta
            checked={fila.estado_alta === 'lista' && seleccion.has(fila.ruc)}
            onChange={() => alternar(fila.ruc)}
            disabled={fila.estado_alta !== 'lista'}
          />
        </div>
      ),
    },
    {
      clave: 'empresa',
      cabecera: 'Empresa',
      cabeceraDeFila: true,
      anchoMinimo: '12rem',
      render: (fila) => (
        <div className={estilos.empresa}>
          {fila.estado_alta === 'requiere_correccion' ? (
            <button
              type="button"
              className={estilos.advertencia}
              onClick={() => setMotivo(fila)}
              aria-label={`Ver por qué ${fila.nombre ?? fila.ruc} requiere corrección`}
              title="Requiere corrección: ver el motivo"
            >
              <IconoAdvertencia />
            </button>
          ) : null}
          <span className={estilos.textoEmpresa}>
            <span>{fila.nombre ?? 'Sin razón social'}</span>
            <span className={estilos.ruc}>{fila.ruc}</span>
            {fila.estado_alta === 'registrando' ? (
              <Badge tono="info" conPunto>
                Registrando
              </Badge>
            ) : null}
          </span>
        </div>
      ),
    },
    {
      clave: 'periodos',
      cabecera: 'Periodos',
      numerica: true,
      render: (fila) => formatearEntero(fila.total_periodos),
    },
    {
      clave: 'sire',
      cabecera: 'Última actualización',
      monoespaciada: true,
      render: (fila) =>
        fila.ultima_actualizacion_sire
          ? formatearFechaHora(fila.ultima_actualizacion_sire)
          : 'Nunca',
    },
    {
      clave: 'ultimo',
      cabecera: 'Último proceso',
      render: (fila) =>
        fila.ultimo_proceso ? (
          presentarTipoJob(fila.ultimo_proceso.tipo)
        ) : (
          <span className={layout.textoSecundario}>Ninguno</span>
        ),
    },
    {
      clave: 'acciones',
      cabecera: 'Acciones',
      render: (fila) => {
        const nombre = fila.nombre ?? fila.ruc;
        const lista = fila.estado_alta === 'lista';
        return (
          <div className={estilos.acciones}>
            {fila.estado_alta === 'requiere_correccion' ? (
              <Button
                pequeno
                variante="primario"
                icono={<IconoLapiz />}
                aria-label={`Corregir RUC, usuario y clave SOL de ${nombre}`}
                onClick={() => setCorregir(fila)}
              >
                Corregir
              </Button>
            ) : (
              <Button
                pequeno
                variante="secundario"
                aria-label={`Entrar al panel de ${nombre}`}
                onClick={() => entrar(fila.ruc)}
                disabled={!lista}
              >
                Entrar
              </Button>
            )}
            {lista ? (
              <Button
                pequeno
                variante="fantasma"
                aria-label={`Ajustes de ${nombre}`}
                onClick={() => entrar(fila.ruc, '/ajustes')}
              >
                Ajustes
              </Button>
            ) : null}
            <button
              type="button"
              className={estilos.basura}
              aria-label={`Eliminar ${nombre}`}
              title="Eliminar empresa"
              onClick={() => setBorrar(fila)}
            >
              <IconoBasura />
            </button>
          </div>
        );
      },
    },
  ];

  const totales = resumen.data?.procesos_por_estado;
  const dias = resumen.data?.dias ?? 30;

  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Empresas"
        descripcion="Estado de cada empresa, sus periodos y los procesos en segundo plano."
        acciones={
          <>
            {esAdmin ? (
              <ButtonLink a="/accesos" variante="fantasma" pequeno>
                Cuentas con acceso
              </ButtonLink>
            ) : null}
            <ButtonLink a="/nueva-empresa" variante="primario" pequeno>
              Registrar empresas
            </ButtonLink>
          </>
        }
      />

      {resumen.isPending ? <Skeleton lineas={6} etiqueta="Cargando las empresas" /> : null}
      {resumen.isError ? (
        <ErrorState
          titulo="No se pudo cargar el resumen"
          texto={
            resumen.error instanceof ApiError ? resumen.error.message : 'Error inesperado.'
          }
          accion={
            <Button pequeno onClick={() => void resumen.refetch()}>
              Reintentar
            </Button>
          }
        />
      ) : null}

      {resumen.data && totales ? (
        <>
          <div className={estilos.metricas}>
            <MetricTile
              etiqueta="Empresas registradas"
              valor={formatearEntero(resumen.data.total_empresas)}
            />
            <MetricTile etiqueta="En cola" valor={formatearEntero(totales.pendiente)} />
            <MetricTile etiqueta="En ejecución" valor={formatearEntero(totales.en_progreso)} />
            <MetricTile
              etiqueta="Completados"
              valor={formatearEntero(totales.completado)}
              nota={`Últimos ${dias} días`}
            />
            <MetricTile
              etiqueta="Con errores"
              valor={formatearEntero(totales.fallido)}
              nota={`Últimos ${dias} días`}
            />
          </div>

          <Panel
            titulo="Empresas"
            acciones={
              marcadas ? (
                <ButtonLink a="/procesamiento" variante="primario" pequeno>
                  Procesar {marcadas} {marcadas === 1 ? 'seleccionada' : 'seleccionadas'}
                </ButtonLink>
              ) : null
            }
          >
            <div className={estilos.herramientas}>
              <div className={estilos.filtro}>
                <TextField
                  etiqueta="Filtrar por RUC o nombre"
                  name="filtro"
                  value={filtro}
                  onChange={(evento) => setFiltro(evento.target.value)}
                />
              </div>
              <div className={estilos.seleccionarTodas}>
                <Checkbox
                  etiqueta={filtro ? 'Seleccionar las filtradas' : 'Seleccionar todas'}
                  checked={
                    seleccionables.length > 0 && visiblesMarcadas === seleccionables.length
                  }
                  indeterminado={
                    visiblesMarcadas > 0 && visiblesMarcadas < seleccionables.length
                  }
                  onChange={alternarVisibles}
                  disabled={!seleccionables.length}
                />
              </div>
            </div>

            <DataTable
              leyenda="Listado de empresas"
              leyendaOculta
              centrada
              columnas={columnas}
              filas={visibles}
              claveDeFila={(fila) => fila.ruc}
              claseDeFila={(fila) =>
                fila.estado_alta === 'lista' ? undefined : estilos.filaBloqueada
              }
              vacio={
                <EmptyState
                  titulo={empresas.length ? 'Ninguna coincide' : 'Todavía no hay empresas'}
                  texto={
                    empresas.length
                      ? 'Prueba con otro RUC o nombre.'
                      : 'Registra la primera para empezar a sincronizar el SIRE.'
                  }
                />
              }
            />
          </Panel>
        </>
      ) : null}

      <Dialog
        abierto={motivo !== null}
        titulo={`${motivo?.nombre ?? motivo?.ruc ?? ''} requiere corrección`}
        texto="No se puede abrir porque Sire no obtuvo sus credenciales del API SUNAT. Este es el motivo:"
        onCerrar={() => setMotivo(null)}
        acciones={
          <>
            <Button variante="fantasma" onClick={() => setMotivo(null)}>
              Cerrar
            </Button>
            <Button
              variante="primario"
              icono={<IconoLapiz />}
              onClick={() => {
                setCorregir(motivo);
                setMotivo(null);
              }}
            >
              Corregir datos
            </Button>
          </>
        }
      >
        {motivo?.motivo_alta ? <p className={estilos.motivo}>{motivo.motivo_alta}</p> : null}
      </Dialog>

      {corregir ? (
        <CorregirEmpresa empresa={corregir} onCerrar={() => setCorregir(null)} />
      ) : null}

      <Dialog
        abierto={borrar !== null}
        titulo={`¿Eliminar ${borrar?.nombre ?? borrar?.ruc ?? ''}?`}
        texto="Se borran sus comprobantes, periodos y ajustes. Esta acción no se puede deshacer."
        onCerrar={() => setBorrar(null)}
        acciones={
          <>
            <Button variante="fantasma" onClick={() => setBorrar(null)}>
              Cancelar
            </Button>
            <Button
              variante="peligro"
              cargando={eliminar.isPending}
              onClick={() => {
                if (borrar) eliminar.mutate(borrar.ruc);
              }}
            >
              Sí, eliminar
            </Button>
          </>
        }
      />
    </div>
  );
}

function IconoAdvertencia() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M10.3 4.2 2.9 17.1A2 2 0 0 0 4.6 20h14.8a2 2 0 0 0 1.7-2.9L13.7 4.2a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9.5v4M12 16.8v.1" />
    </svg>
  );
}

function IconoLapiz() {
  return (
    <svg className={estilos.iconoBoton} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3Z" />
      <path d="m14.5 7.5 3 3" />
    </svg>
  );
}

function IconoBasura() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M4.5 7h15M9.5 7V5h5v2M6.5 7l1 12.5a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5l1-12.5" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

function filtrar(empresas: readonly ResumenEmpresa[], filtro: string): ResumenEmpresa[] {
  const texto = filtro.trim().toLowerCase();
  if (!texto) return [...empresas];
  return empresas.filter(
    (e) => e.ruc.includes(texto) || (e.nombre ?? '').toLowerCase().includes(texto),
  );
}
