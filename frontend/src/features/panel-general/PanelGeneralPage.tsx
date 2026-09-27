import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

import { obtenerResumenEmpresas } from '@/api/empresas';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { type Columna, DataTable } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { useAuth } from '@/features/auth/useAuth';
import { ANCLA_CORREOS } from '@/features/empresa/correos';
import { presentarEstadoJob, presentarTipoJob } from '@/features/jobs/estadoJob';
import { useEsAdmin } from '@/features/usuarios/useEsAdmin';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { formatearEntero, formatearFechaHora, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import { guardarEmpresaActiva, obtenerSesion } from '@/lib/session';
import layout from '@/styles/layouts.module.css';
import type { ResumenEmpresa } from '@/types/api';

import { ETIQUETA_LIBRO, PERIODOS_VISIBLES } from './etiquetas';
import { HistorialDescargas } from './HistorialDescargas';
import estilos from './PanelGeneralPage.module.css';

const INTERVALO_MS = 5000;

/**
 * Todas las empresas de un vistazo: cuántas hay, sus periodos, cuándo se bajó
 * por última vez su SIRE, su último proceso y a quién se envían sus
 * resultados. Vive fuera del armazón porque no es de ninguna empresa.
 */
export function PanelGeneralPage() {
  useDocumentTitle('Todas las empresas');
  const navegar = useNavigate();
  const { correo, salir } = useAuth();
  const esAdmin = useEsAdmin();
  const [filtro, setFiltro] = useState('');

  const resumen = useQuery({
    queryKey: ['resumen-empresas'],
    queryFn: obtenerResumenEmpresas,
    // Mientras haya procesos vivos el panel se refresca solo; después, no.
    refetchInterval: (consulta) => {
      const vivos = consulta.state.data?.procesos_por_estado;
      return vivos && vivos.pendiente + vivos.en_progreso > 0 ? INTERVALO_MS : false;
    },
  });

  const empresas = useMemo(() => resumen.data?.empresas ?? [], [resumen.data]);
  const nombres = useMemo(
    () => new Map(empresas.map((e) => [e.ruc, e.nombre ?? e.ruc] as const)),
    [empresas],
  );
  const visibles = filtrar(empresas, filtro);
  const activa = obtenerSesion()?.ruc ?? null;

  function entrar(ruc: string, destino = '/') {
    guardarEmpresaActiva(ruc);
    void navegar(destino);
  }

  const columnas: readonly Columna<ResumenEmpresa>[] = [
    {
      clave: 'empresa',
      cabecera: 'Empresa',
      cabeceraDeFila: true,
      anchoMinimo: '14rem',
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
      anchoMinimo: '14rem',
      render: (fila) =>
        fila.total_periodos ? (
          <div className={estilos.periodos}>
            <span>{formatearEntero(fila.total_periodos)}</span>
            {fila.periodos.slice(0, PERIODOS_VISIBLES).map((p) => (
              <Badge key={p.periodo} tono={p.estado === 'sincronizado' ? 'exito' : 'neutro'}>
                {formatearPeriodo(p.periodo)}
                <span className="visually-hidden">
                  {p.estado === 'sincronizado'
                    ? ', sincronizado'
                    : `, ${p.estado ?? 'pendiente'}`}
                </span>
              </Badge>
            ))}
            {fila.total_periodos > PERIODOS_VISIBLES ? (
              <span className={layout.textoSecundario}>
                +{fila.total_periodos - PERIODOS_VISIBLES} más
              </span>
            ) : null}
          </div>
        ) : (
          <span className={layout.textoSecundario}>Sin periodos</span>
        ),
    },
    {
      clave: 'sire',
      cabecera: 'Última actualización SIRE',
      monoespaciada: true,
      render: (fila) =>
        fila.ultima_actualizacion_sire
          ? formatearFechaHora(fila.ultima_actualizacion_sire)
          : 'Nunca',
    },
    {
      clave: 'ultimo',
      cabecera: 'Último proceso',
      anchoMinimo: '14rem',
      render: (fila) => {
        const job = fila.ultimo_proceso;
        if (!job) return <span className={layout.textoSecundario}>Ninguno</span>;
        const estado = presentarEstadoJob(job.estado);
        const detalle = [
          presentarTipoJob(job.tipo),
          job.periodo ? formatearPeriodo(job.periodo) : null,
          job.libro ? ETIQUETA_LIBRO[job.libro] : null,
        ]
          .filter(Boolean)
          .join(' · ');
        return (
          <>
            <Badge tono={estado.tono} conPunto>
              {estado.texto}
            </Badge>
            <br />
            <span className={layout.textoSecundario}>{detalle}</span>
            {job.error ? <p className={estilos.error}>{job.error}</p> : null}
          </>
        );
      },
    },
    {
      clave: 'correos',
      cabecera: 'Correos de envío',
      anchoMinimo: '14rem',
      render: (fila) => (
        <div className={estilos.correos}>
          {fila.correos_notificacion.length ? (
            <ul className={estilos.listaCorreos}>
              {fila.correos_notificacion.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            <span className={layout.textoSecundario}>Sin correos</span>
          )}
          <Button
            pequeno
            variante="fantasma"
            aria-label={`Editar los correos de ${fila.nombre ?? fila.ruc}`}
            onClick={() => entrar(fila.ruc, `/ajustes#${ANCLA_CORREOS}`)}
          >
            Editar
          </Button>
        </div>
      ),
    },
    {
      clave: 'acciones',
      cabecera: 'Acciones',
      render: (fila) => (
        <Button
          pequeno
          variante="secundario"
          aria-label={`Entrar al panel de ${fila.nombre ?? fila.ruc}`}
          onClick={() => entrar(fila.ruc)}
        >
          Entrar
        </Button>
      ),
    },
  ];

  const totales = resumen.data?.procesos_por_estado;
  const dias = resumen.data?.dias ?? 30;

  return (
    <main className={estilos.pagina}>
      <header className={estilos.barra}>
        <p className={estilos.marca}>Sire · SUNAT</p>
        <div className={estilos.herramientas}>
          {correo ? <span className={layout.textoSecundario}>{correo}</span> : null}
          <ThemeToggle />
          <Button pequeno variante="fantasma" onClick={salir}>
            Cerrar sesión
          </Button>
        </div>
      </header>

      <div className={estilos.contenido}>
        <div className={estilos.cabecera}>
          <div>
            <h1 className={estilos.titulo}>Todas las empresas</h1>
            <p className={layout.textoSecundario}>
              Estado de cada empresa, sus periodos y los procesos en segundo plano.
            </p>
          </div>
          <div className={layout.fila}>
            {activa ? (
              <ButtonLink a="/" variante="fantasma" pequeno>
                Volver a {nombres.get(activa) ?? activa}
              </ButtonLink>
            ) : null}
            {esAdmin ? (
              <ButtonLink a="/accesos" variante="fantasma" pequeno>
                Cuentas con acceso
              </ButtonLink>
            ) : null}
            <ButtonLink a="/empresas/nueva" variante="primario" pequeno>
              Registrar empresas
            </ButtonLink>
          </div>
        </div>

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
          <div className={layout.pilaAmplia}>
            <div className={layout.rejillaMetricas}>
              <MetricTile
                etiqueta="Empresas registradas"
                valor={formatearEntero(resumen.data.total_empresas)}
              />
              <MetricTile etiqueta="En cola" valor={formatearEntero(totales.pendiente)} />
              <MetricTile
                etiqueta="En ejecución"
                valor={formatearEntero(totales.en_progreso)}
              />
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
                <TextField
                  etiqueta="Filtrar por RUC o nombre"
                  name="filtro"
                  value={filtro}
                  onChange={(evento) => setFiltro(evento.target.value)}
                />
              }
            >
              <DataTable
                leyenda="Listado de empresas"
                leyendaOculta
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

            <HistorialDescargas nombres={nombres} />
          </div>
        ) : null}
      </div>
    </main>
  );
}

function filtrar(empresas: readonly ResumenEmpresa[], filtro: string): ResumenEmpresa[] {
  const texto = filtro.trim().toLowerCase();
  if (!texto) return [...empresas];
  return empresas.filter(
    (e) => e.ruc.includes(texto) || (e.nombre ?? '').toLowerCase().includes(texto),
  );
}
