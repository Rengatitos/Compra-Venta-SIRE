import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { ReactNode } from 'react';

import {
  consultarDetracciones,
  descargarDetracciones,
  disponibilidadDetracciones,
  listarNpds,
  descargarPdfNpd,
} from '@/api/detracciones';
import type { NpdPeriodo } from '@/api/detracciones';
import { obtenerJob } from '@/api/jobs';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Panel } from '@/components/ui/Panel';
import { formatearMoneda } from '@/lib/format';
import { useJobs } from '@/features/jobs/useJobs';
import { useToast } from '@/hooks/useToast';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteResponse } from '@/types/api';

import estilos from './Detracciones.module.css';
import { humanizarClave, normalizarNpd, presentarEstadoNpd, soloFecha } from './npd';
import { Dato, Seccion } from './Seccion';

export function DescargarDetraccionesButton({
  ruc,
  periodo,
}: {
  ruc: string;
  periodo: string;
}) {
  const { seguir } = useJobs();
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const [avance, setAvance] = useState('');
  const disponibilidad = useQuery({
    queryKey: ['comprobantes', ruc, periodo, 'detracciones-disponibles'],
    queryFn: () => disponibilidadDetracciones(ruc, periodo),
  });
  const habilitado = disponibilidad.data?.disponible === true && !disponibilidad.isError;
  const descarga = useMutation({
    mutationFn: async () => {
      const aceptado = await consultarDetracciones(ruc, periodo);
      seguir(aceptado.job_id);
      for (;;) {
        const job = await obtenerJob(aceptado.job_id);
        setAvance(job.progreso.mensaje || 'Esperando turno en SUNAT…');
        if (job.estado === 'fallido')
          throw new Error(job.error || 'Falló la consulta de detracciones');
        if (job.estado === 'completado') break;
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
      }
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo, 'npds'] });
      await descargarDetracciones(ruc, periodo);
      mostrar({
        tono: 'exito',
        titulo: 'NPD descargados',
        detalle: 'ZIP con los PDF disponibles del periodo.',
      });
    },
    onError: (error) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudieron descargar las detracciones',
        detalle: error instanceof Error ? error.message : 'Error inesperado.',
      }),
  });
  return (
    <div>
      <Button
        cargando={descarga.isPending}
        disabled={!habilitado}
        onClick={() => descarga.mutate()}
      >
        Descargar NPD del periodo
      </Button>
      {descarga.isPending ? <p role="status">{avance || 'Iniciando consulta…'}</p> : null}
    </div>
  );
}

const ETIQUETAS: Record<string, string> = {
  num_constancia: 'Constancia',
  num_npd: 'NPD',
  numNpd: 'NPD',
  des_prov: 'Proveedor',
  desProv: 'Proveedor',
  num_ruc_proveedor: 'RUC del proveedor',
  numRucProveedor: 'RUC del proveedor',
  des_adq: 'Adquiriente',
  desAdq: 'Adquiriente',
  num_doc_adq: 'RUC del adquiriente',
  numDocAdq: 'RUC del adquiriente',
  mto_deposito: 'Importe depositado',
  mtoDeposito: 'Importe depositado',
  mto_deposito_desc: 'Importe depositado',
  fec_pago_desc: 'Fecha de pago',
  fechaPago: 'Fecha de pago',
  num_cuenta: 'Cuenta de detracciones',
  numCuenta: 'Cuenta de detracciones',
  num_serie: 'Serie',
  numSerie: 'Serie',
  num_comprobante: 'Número de comprobante',
  numComprobante: 'Número de comprobante',
  per_tributario: 'Periodo tributario',
  perTributario: 'Periodo tributario',
  estado: 'Estado',
  importe: 'Importe',
  listadepositoDetInternet: 'Depósitos relacionados',
  consultarNPD: 'Información del NPD',
  resultadoInfoNPD: 'Información del NPD',
  cabeceraInternet: 'Resumen del NPD',
};

function Valor({ valor }: { valor: unknown }) {
  if (Array.isArray(valor)) {
    const elementos: unknown[] = valor;
    return (
      <>
        {elementos.map((item, i) => (
          <div key={i}>
            <Valor valor={item} />
          </div>
        ))}
      </>
    );
  }
  if (valor !== null && typeof valor === 'object')
    return <Campos datos={valor as Record<string, unknown>} />;
  if (typeof valor === 'string' || typeof valor === 'number') return <>{valor}</>;
  if (typeof valor === 'boolean') return <>{valor ? 'Sí' : 'No'}</>;
  return <>—</>;
}

/**
 * Volcado genérico, reservado para lo que el portal mande fuera de la forma
 * conocida. Todo lo que sí tiene forma se pinta con secciones de verdad.
 */
function Campos({ datos }: { datos: Record<string, unknown> }) {
  return (
    <dl className={estilos.campos}>
      {Object.entries(datos).map(([clave, valor]) => (
        <div key={clave}>
          <dt>{ETIQUETAS[clave] ?? humanizarClave(clave)}</dt>
          <dd>
            <Valor valor={valor} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function DetraccionCelda({ fila }: { fila: ComprobanteResponse }) {
  return <>{fila.detraccion ? 'Sí' : 'No'}</>;
}

/** Cuerpo del modal de un NPD: resumen, datos del portal y sus depósitos. */
function FichaNpd({ npd }: { npd: NpdPeriodo }) {
  const datos = normalizarNpd(npd);

  return (
    <>
      <Seccion
        titulo="Resumen"
        acciones={
          <Badge tono={datos.estado.tono} conPunto>
            {datos.estado.texto}
          </Badge>
        }
      >
        <dl className={layout.definiciones}>
          <Dato termino="Importe">{formatearMoneda(datos.importe, 'PEN')}</Dato>
          <Dato termino="Generado por">{datos.generadoPor || '—'}</Dato>
          <Dato termino="Registro">{datos.registro || '—'}</Dato>
          <Dato termino="Creación">{datos.creacion || '—'}</Dato>
          <Dato termino="Vencimiento">{datos.vencimiento || '—'}</Dato>
        </dl>
      </Seccion>

      {datos.datosPortal.length > 0 ? (
        <Seccion titulo="Datos del NPD">
          <dl className={layout.definiciones}>
            {datos.datosPortal.map((dato) => (
              <Dato key={dato.clave} termino={dato.etiqueta}>
                {dato.valor}
              </Dato>
            ))}
          </dl>
        </Seccion>
      ) : null}

      {datos.depositos.length > 0 ? (
        <Seccion titulo="Depósitos de detracciones">
          {datos.depositos.map((deposito) => (
            <article key={deposito.indice} className={estilos.deposito}>
              <div className={estilos.depositoCabecera}>
                <h4 className={estilos.depositoTitulo}>{deposito.titulo}</h4>
                {deposito.monto ? (
                  <p className={estilos.depositoMonto}>{deposito.monto}</p>
                ) : null}
              </div>
              <dl className={layout.definiciones}>
                {deposito.campos.map((campo) => (
                  <Dato key={campo.clave} termino={campo.etiqueta}>
                    {campo.valor}
                  </Dato>
                ))}
              </dl>
            </article>
          ))}
        </Seccion>
      ) : null}

      {datos.otrosListado.length > 0 ? (
        <Seccion titulo="Otros datos del listado">
          <dl className={layout.definiciones}>
            {datos.otrosListado.map((dato) => (
              <Dato key={dato.clave} termino={dato.etiqueta}>
                {dato.valor || '—'}
              </Dato>
            ))}
          </dl>
        </Seccion>
      ) : null}

      {Object.keys(datos.restoDetalle).length > 0 ? (
        <Seccion titulo="Resto del detalle">
          <Campos datos={datos.restoDetalle} />
        </Seccion>
      ) : null}
    </>
  );
}

export function NpdPanel({
  ruc,
  periodo,
  acciones,
}: {
  ruc: string;
  periodo: string;
  /** Acciones del panel, p. ej. el botón que consulta y descarga los NPD. */
  acciones?: ReactNode;
}) {
  const [seleccionado, setSeleccionado] = useState<NpdPeriodo | null>(null);
  const { mostrar } = useToast();
  const consulta = useQuery({
    queryKey: ['comprobantes', ruc, periodo, 'npds'],
    queryFn: () => listarNpds(ruc, periodo),
  });
  const pdf = useMutation({
    mutationFn: (numero: string) => descargarPdfNpd(ruc, periodo, numero),
    onError: (error) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo descargar el PDF',
        detalle: error instanceof Error ? error.message : 'Error inesperado.',
      }),
  });
  const columnas: Columna<NpdPeriodo>[] = [
    {
      clave: 'numero',
      cabecera: 'NPD',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => (
        <button type="button" className={estilos.enlace} onClick={() => setSeleccionado(fila)}>
          {fila.numero}
        </button>
      ),
    },
    {
      clave: 'registro',
      cabecera: 'Registro',
      // La hora del registro solo sale en la ficha: en la tabla no aporta.
      render: (fila) => soloFecha(fila.cabecera.fecRegistro) || '—',
    },
    {
      clave: 'creacion',
      cabecera: 'Creación',
      render: (fila) => soloFecha(fila.cabecera.fecCreacion) || '—',
    },
    {
      clave: 'limite',
      cabecera: 'Vencimiento',
      render: (fila) => soloFecha(fila.cabecera.fecLimitePago) || '—',
    },
    {
      clave: 'importe',
      cabecera: 'Importe',
      numerica: true,
      render: (fila) =>
        fila.cabecera.importe == null ? '—' : formatearMoneda(fila.cabecera.importe, 'PEN'),
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (fila) => {
        const estado = presentarEstadoNpd(fila.cabecera.estado);
        return (
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        );
      },
    },
    {
      clave: 'descarga',
      cabecera: 'Descarga',
      render: (fila) => (
        <div>
          <Button
            pequeno
            disabled={!fila.pdf_ruta || pdf.isPending}
            onClick={() => pdf.mutate(fila.numero)}
            title={fila.error_pdf ?? `Descargar PDF del NPD ${fila.numero}`}
          >
            Descargar PDF
          </Button>

          {fila.error_pdf ? <p className={layout.textoSecundario}>{fila.error_pdf}</p> : null}
        </div>
      ),
    },
  ];
  return (
    <Panel
      titulo="NPD del periodo"
      descripcion="Números de Pago de Detracciones registrados en el mes. Selecciona un número para ver su detalle."
      acciones={acciones}
    >
      {consulta.isPending ? <p role="status">Cargando NPD…</p> : null}
      {consulta.isError ? (
        <p role="alert">
          No se pudieron cargar los NPD.{' '}
          <Button onClick={() => void consulta.refetch()}>Reintentar</Button>
        </p>
      ) : null}
      {consulta.data ? (
        <DataTable
          leyenda="NPD del periodo"
          leyendaOculta
          columnas={columnas}
          filas={consulta.data.npds}
          claveDeFila={(fila) => fila.numero}
          vacio={
            <p>
              {consulta.data.consultado_en
                ? 'SUNAT no devolvió NPD para este periodo.'
                : 'Todavía no se ha completado la consulta de NPD del periodo.'}
            </p>
          }
        />
      ) : null}
      <Dialog
        abierto={seleccionado !== null}
        titulo={`NPD ${seleccionado?.numero ?? ''}`}
        ancho="amplio"
        onCerrar={() => setSeleccionado(null)}
        acciones={<Button onClick={() => setSeleccionado(null)}>Cerrar</Button>}
      >
        {seleccionado ? <FichaNpd npd={seleccionado} /> : null}
      </Dialog>
    </Panel>
  );
}
