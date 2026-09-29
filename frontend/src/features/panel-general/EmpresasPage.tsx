import { useState } from 'react';
import { useNavigate } from 'react-router';

import { PageHeader } from '@/components/layout/PageHeader';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { type Columna, DataTable } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { presentarTipoJob } from '@/features/jobs/estadoJob';
import { useEsAdmin } from '@/features/usuarios/useEsAdmin';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { formatearEntero, formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';
import { guardarEmpresaActiva } from '@/lib/session';
import layout from '@/styles/layouts.module.css';
import type { ResumenEmpresa } from '@/types/api';

import estilos from './EmpresasPage.module.css';
import { useSeleccion } from './seleccionContext';
import { useResumenEmpresas } from './useResumenEmpresas';

/**
 * Todas las empresas de un vistazo: cuántas hay, sus periodos, cuándo se bajó
 * por última vez su SIRE, su último proceso y a quién se envían sus
 * resultados. Es la pantalla de entrada; aquí se marcan las empresas que luego
 * se lanzan desde «Procesamiento masivo».
 */
export function EmpresasPage() {
  useDocumentTitle('Empresas');
  const navegar = useNavigate();
  const esAdmin = useEsAdmin();
  const [filtro, setFiltro] = useState('');
  const { seleccion, setSeleccion } = useSeleccion();
  const { resumen, empresas } = useResumenEmpresas();

  const visibles = filtrar(empresas, filtro);

  function entrar(ruc: string, destino = '/dashboard') {
    guardarEmpresaActiva(ruc);
    void navegar(destino);
  }

  // La selección sobrevive al filtro: filtrar sirve para encontrar y marcar,
  // no para desmarcar lo que ya se eligió.
  const marcadas = empresas.filter((e) => seleccion.has(e.ruc)).length;
  const visiblesMarcadas = visibles.filter((e) => seleccion.has(e.ruc)).length;

  function alternar(ruc: string) {
    const nueva = new Set(seleccion);
    if (nueva.has(ruc)) nueva.delete(ruc);
    else nueva.add(ruc);
    setSeleccion(nueva);
  }

  function alternarVisibles() {
    const nueva = new Set(seleccion);
    const todasVisibles = visibles.length > 0 && visiblesMarcadas === visibles.length;
    for (const e of visibles) {
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
            checked={seleccion.has(fila.ruc)}
            onChange={() => alternar(fila.ruc)}
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
        <>
          <span>{fila.nombre ?? 'Sin razón social'}</span>
          <br />
          <span className={estilos.ruc}>{fila.ruc}</span>
        </>
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
      render: (fila) => (
        <div className={estilos.acciones}>
          <Button
            pequeno
            variante="secundario"
            aria-label={`Entrar al panel de ${fila.nombre ?? fila.ruc}`}
            onClick={() => entrar(fila.ruc)}
          >
            Entrar
          </Button>
          <Button
            pequeno
            variante="fantasma"
            aria-label={`Ajustes de ${fila.nombre ?? fila.ruc}`}
            onClick={() => entrar(fila.ruc, '/ajustes')}
          >
            Ajustes
          </Button>
        </div>
      ),
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
                  checked={visibles.length > 0 && visiblesMarcadas === visibles.length}
                  indeterminado={visiblesMarcadas > 0 && visiblesMarcadas < visibles.length}
                  onChange={alternarVisibles}
                  disabled={!visibles.length}
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
    </div>
  );
}

function filtrar(empresas: readonly ResumenEmpresa[], filtro: string): ResumenEmpresa[] {
  const texto = filtro.trim().toLowerCase();
  if (!texto) return [...empresas];
  return empresas.filter(
    (e) => e.ruc.includes(texto) || (e.nombre ?? '').toLowerCase().includes(texto),
  );
}
