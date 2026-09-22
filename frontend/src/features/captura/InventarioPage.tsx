import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';

import {
  accionLote,
  cargarDocumento,
  conciliarPeriodo,
  crearLote,
  exportarInventario,
  listarDocumentos,
  listarPeriodosCaptura,
  obtenerLote,
} from '@/api/captura';
import type { Documento } from '@/api/captura';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { TextField, SelectField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import layout from '@/styles/layouts.module.css';
import styles from './Inventario.module.css';

const valor = (doc: Documento, key: string) => doc.extracted?.fields[key]?.value ?? '—';

export function InventarioPage() {
  useDocumentTitle('Inventario de comprobantes');
  const ruc = useRuc();
  const client = useQueryClient();
  const { id: batchId } = useParams();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [tipo, setTipo] = useState('');
  const [order, setOrder] = useState('received_at');
  const [message, setMessage] = useState('');
  const period = params.get('periodo') ?? '';
  const observed = params.get('observados') === 'true';
  const duplicates = params.get('duplicados') === 'true';
  const documents = useQuery({
    queryKey: [
      'captura',
      ruc,
      'documents',
      batchId,
      period,
      q,
      status,
      tipo,
      observed,
      duplicates,
      page,
      order,
    ],
    queryFn: () =>
      listarDocumentos({
        period,
        q,
        status,
        type: tipo,
        observed,
        duplicates,
        batch_id: batchId,
        page,
        sort: order,
      }),
    refetchInterval: 5000,
  });
  const periods = useQuery({
    queryKey: ['captura', ruc, 'periods'],
    queryFn: listarPeriodosCaptura,
  });
  const batch = useQuery({
    queryKey: ['captura', ruc, 'batch', batchId],
    queryFn: () => obtenerLote(batchId!),
    enabled: Boolean(batchId),
    refetchInterval: 5000,
  });
  const refresh = () => client.invalidateQueries({ queryKey: ['captura', ruc] });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      let target = batchId;
      if (files.length > 1 && !target) {
        if (!period) throw new Error('Selecciona el periodo antes de cargar varios archivos.');
        target = (await crearLote(period)).id;
      }
      let loaded = 0;
      const errors: string[] = [];
      for (const file of files) {
        try {
          await cargarDocumento(file, target);
          loaded++;
        } catch (error) {
          errors.push(`${file.name}: ${error instanceof Error ? error.message : 'Error'}`);
        }
      }
      if (target && !batchId) await accionLote(target, 'close');
      return `Recibidos: ${loaded}. ${errors.join(' ')}`;
    },
    onSuccess: async (text) => {
      setMessage(text);
      await refresh();
    },
    onError: (error) => setMessage(error.message),
  });
  const operation = useMutation({
    mutationFn: async (kind: string) => {
      if (kind === 'export') {
        await exportarInventario(period);
        return 'Exportación descargada.';
      }
      if (kind === 'reconcile') {
        const result = await conciliarPeriodo(period);
        return `Coincidencias sugeridas: ${result.suggested}. Revisa el detalle de los documentos.`;
      }
      const result = await accionLote(batchId!, kind === 'close' ? 'close' : 'confirm');
      return result.message ?? 'Lote cerrado. Procesando…';
    },
    onSuccess: async (text) => {
      setMessage(text);
      await refresh();
    },
    onError: (error) => setMessage(error.message),
  });
  function filter(key: string, value: string) {
    setPage(1);
    setParams((current) => {
      if (value) current.set(key, value);
      else current.delete(key);
      return current;
    });
  }
  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo={batchId ? `Lote #${batchId.slice(0, 8)}` : 'Inventario de comprobantes'}
        descripcion="Documentos recibidos por WhatsApp y cargas web, organizados por periodo contable."
        acciones={<Link to="/lotes">Ver lotes</Link>}
      />
      {batch.data && (
        <Panel titulo={`Periodo ${batch.data.accounting_period}`}>
          <p>
            Estado: {batch.data.status} · Recibidos: {batch.data.received_count}
          </p>
          <div className={layout.fila}>
            <Button
              disabled={batch.data.status !== 'RECEIVING' || operation.isPending}
              onClick={() => operation.mutate('close')}
            >
              Cerrar recepción
            </Button>
            <Button
              disabled={
                !['READY_FOR_REVIEW', 'PARTIALLY_CONFIRMED'].includes(batch.data.status) ||
                operation.isPending
              }
              onClick={() => operation.mutate('confirm')}
            >
              Confirmar válidos
            </Button>
          </div>
          <p>
            {Object.entries(batch.data.counts ?? {})
              .map(([key, count]) => `${key}: ${count}`)
              .join(' · ')}
          </p>
        </Panel>
      )}
      <Panel titulo="Periodos y filtros">
        <div className={layout.fila}>
          {(periods.data ?? [])
            .filter((item) => item._id)
            .map((item) => (
              <Button
                key={item._id}
                pequeno
                aria-pressed={period === item._id}
                onClick={() => filter('periodo', item._id!)}
              >
                {item._id?.slice(0, 4)} / {item._id?.slice(4)} ({item.count})
              </Button>
            ))}
        </div>
        <div className={layout.rejillaFormulario}>
          <TextField
            etiqueta="Periodo contable"
            type="month"
            value={period ? `${period.slice(0, 4)}-${period.slice(4)}` : ''}
            onChange={(event) => filter('periodo', event.target.value.replace('-', ''))}
          />
          <TextField
            etiqueta="Buscar RUC, proveedor, documento o concepto"
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
          />
          <SelectField
            etiqueta="Estado"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
            opciones={[
              { valor: '', texto: 'Todos' },
              ...[
                'QUEUED',
                'OCR_PROCESSING',
                'READY',
                'NEEDS_REVIEW',
                'CONFIRMED',
                'FAILED',
                'CANCELLED',
              ].map((key) => ({ valor: key, texto: key })),
            ]}
          />
          <SelectField
            etiqueta="Tipo"
            value={tipo}
            onChange={(event) => {
              setTipo(event.target.value);
              setPage(1);
            }}
            opciones={[
              { valor: '', texto: 'Todos' },
              ...[
                'FACTURA',
                'BOLETA',
                'NOTA_CREDITO',
                'HONORARIOS',
                'YAPE_TRANSFER',
                'YAPE_SERVICE_PAYMENT',
                'PLIN_TRANSFER',
                'POS_VOUCHER',
                'UNKNOWN',
              ].map((key) => ({ valor: key, texto: key })),
            ]}
          />
          <SelectField
            etiqueta="Ordenar por"
            value={order}
            onChange={(event) => setOrder(event.target.value)}
            opciones={[
              { valor: 'received_at', texto: 'Fecha de ingreso' },
              { valor: 'document_date', texto: 'Fecha documental' },
              { valor: 'accounting_period', texto: 'Periodo' },
            ]}
          />
          <TextField
            etiqueta="Cargar documentos"
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp,application/pdf"
            disabled={
              upload.isPending || Boolean(batchId && batch.data?.status !== 'RECEIVING')
            }
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length) upload.mutate(files);
              event.target.value = '';
            }}
          />
        </div>
        <div className={layout.fila}>
          <label>
            <input
              type="checkbox"
              checked={observed}
              onChange={(event) => filter('observados', event.target.checked ? 'true' : '')}
            />{' '}
            Solo observados
          </label>
          <label>
            <input
              type="checkbox"
              checked={duplicates}
              onChange={(event) => filter('duplicados', event.target.checked ? 'true' : '')}
            />{' '}
            Posibles duplicados
          </label>
          <Button
            disabled={!period || operation.isPending}
            onClick={() => operation.mutate('export')}
          >
            Exportar confirmados
          </Button>
          <Button
            disabled={!period || operation.isPending}
            onClick={() => operation.mutate('reconcile')}
          >
            Buscar medios de pago
          </Button>
        </div>
      </Panel>
      <p role="status">{upload.isPending ? 'Cargando documentos…' : message}</p>
      {documents.error && <p role="alert">{documents.error.message}</p>}
      {batch.error && <p role="alert">{batch.error.message}</p>}
      <Panel titulo={`Documentos (${documents.data?.total ?? 0})`}>
        <div
          className={styles.tablaContenedor}
          role="region"
          tabIndex={0}
          aria-label="Inventario de comprobantes"
        >
          <table className={styles.tabla}>
            <thead>
              <tr>
                {[
                  'Estado',
                  'Fecha documento',
                  'Fecha ingreso',
                  'Tipo',
                  'SUNAT',
                  'Serie / Número',
                  'RUC',
                  'Proveedor / Cliente',
                  'Glosa',
                  'Total',
                  'Medio de pago',
                  'Operación',
                  'Periodo',
                  'Origen',
                  'Lote',
                ].map((title) => (
                  <th scope="col" className={styles.celda} key={title}>
                    {title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {documents.data?.items.map((doc) => (
                <tr key={doc.id}>
                  <td className={styles.celda}>
                    <Link to={`/comprobantes/${doc.id}`}>{doc.status}</Link>
                  </td>
                  {[
                    doc.document_date ?? 'Sin fecha',
                    new Date(doc.received_at).toLocaleString('es-PE'),
                    doc.document_type ?? 'Procesando',
                    doc.sunat_code ?? '—',
                    `${valor(doc, 'document.series')}-${valor(doc, 'document.number')}`,
                    valor(doc, 'issuer.ruc'),
                    valor(doc, 'issuer.name'),
                    valor(doc, 'service.description'),
                    valor(doc, 'amounts.total'),
                    valor(doc, 'payment.channel') !== '—'
                      ? valor(doc, 'payment.channel')
                      : valor(doc, 'payment.method'),
                    valor(doc, 'payment.operation_number'),
                    doc.accounting_period ?? 'Sin asignar',
                    doc.source,
                  ].map((text, index) => (
                    <td className={styles.celda} key={index}>
                      {text}
                    </td>
                  ))}
                  <td className={styles.celda}>
                    {doc.batch_id ? (
                      <Link to={`/lotes/${doc.batch_id}`}>#{doc.batch_id.slice(0, 8)}</Link>
                    ) : (
                      'Individual'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!documents.isLoading && !documents.data?.items.length && (
          <p>No hay documentos con estos filtros.</p>
        )}
        <div className={layout.fila}>
          <Button disabled={page === 1} onClick={() => setPage(page - 1)}>
            Anterior
          </Button>
          <span>Página {page}</span>
          <Button
            disabled={page * 25 >= (documents.data?.total ?? 0)}
            onClick={() => setPage(page + 1)}
          >
            Siguiente
          </Button>
        </div>
      </Panel>
    </div>
  );
}
