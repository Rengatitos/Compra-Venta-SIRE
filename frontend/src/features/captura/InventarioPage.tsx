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
  resumenPeriodoCaptura,
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
import { tiposDocumento } from './catalogo';

const valor = (doc: Documento, key: string) => doc.extracted?.fields[key]?.value ?? '—';

export function InventarioPage() {
  useDocumentTitle('Inventario de comprobantes');
  const ruc = useRuc();
  const client = useQueryClient();
  const { id: batchId } = useParams();
  const [params, setParams] = useSearchParams();
  const [message, setMessage] = useState('');
  const period = params.get('periodo') ?? '';
  const observed = params.get('observados') === 'true';
  const duplicates = params.get('duplicados') === 'true';
  const requestedPage = Number(params.get('pagina') ?? 1);
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const q = params.get('q') ?? '';
  const status = observed ? '' : (params.get('estado') ?? '');
  const tipo = params.get('tipo') ?? '';
  const requestedOrder = params.get('orden') ?? 'received_at';
  const order = ['received_at', 'document_date', 'accounting_period'].includes(requestedOrder)
    ? requestedOrder
    : 'received_at';
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
  const operationPeriod = period || batch.data?.accounting_period || '';
  const summary = useQuery({
    queryKey: ['captura', ruc, 'summary', operationPeriod],
    queryFn: () => resumenPeriodoCaptura(operationPeriod),
    enabled: /^\d{4}(0[1-9]|1[0-2])$/.test(operationPeriod),
    refetchInterval: 5000,
  });
  const countStatus = (statuses: string[]) =>
    (summary.data ?? []).reduce(
      (sum, item) => sum + (statuses.includes(item._id.status) ? item.count : 0),
      0,
    );
  const countsByType = (summary.data ?? []).reduce<Record<string, number>>((counts, item) => {
    const type = item._id.type ?? 'UNKNOWN';
    counts[type] = (counts[type] ?? 0) + item.count;
    return counts;
  }, {});
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
        await exportarInventario(operationPeriod);
        return 'Exportación descargada.';
      }
      if (kind === 'reconcile') {
        const result = await conciliarPeriodo(operationPeriod);
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
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (key !== 'pagina') next.delete('pagina');
      if (key === 'observados' && value) next.delete('estado');
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  }
  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo={batchId ? `Lote #${batchId.slice(0, 8)}` : 'Inventario de comprobantes'}
        descripcion="Documentos recibidos por WhatsApp y cargas web, organizados por periodo contable."
        acciones={<Link to="/lotes">Ver lotes</Link>}
      />
      {summary.data && (
        <Panel titulo={`Resumen del periodo ${operationPeriod}`}>
          <dl className={layout.fila}>
            <div><dt>Total recibidos</dt><dd>{summary.data.reduce((sum, item) => sum + item.count, 0)}</dd></div>
            <div><dt>Listos para confirmar</dt><dd>{countStatus(['READY'])}</dd></div>
            <div><dt>Observados</dt><dd>{countStatus(['NEEDS_REVIEW', 'FAILED'])}</dd></div>
            <div><dt>Confirmados</dt><dd>{countStatus(['CONFIRMED', 'EXPORTED'])}</dd></div>
          </dl>
          <p>Incluye todos los documentos del periodo, independientemente de los filtros y del lote.</p>
          <ul>
            {Object.entries(countsByType).map(([type, count]) => (
              <li key={type}>{tiposDocumento.find((item) => item.valor === type)?.texto ?? type}: {count}</li>
            ))}
          </ul>
        </Panel>
      )}
      {summary.error && <p role="alert">{summary.error.message}</p>}
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
            onChange={(event) => filter('q', event.target.value)}
          />
          <SelectField
            etiqueta="Estado"
            value={status}
            disabled={observed}
            ayuda={observed ? 'Solo observados incluye documentos por revisar y fallidos.' : undefined}
            onChange={(event) => filter('estado', event.target.value)}
            opciones={[
              { valor: '', texto: 'Todos' },
              ...[
                'QUEUED',
                'OCR_PROCESSING',
                'READY',
                'NEEDS_REVIEW',
                'CONFIRMED',
                'EXPORTED',
                'FAILED',
                'CANCELLED',
              ].map((key) => ({ valor: key, texto: key })),
            ]}
          />
          <SelectField
            etiqueta="Tipo"
            value={tipo}
            onChange={(event) => filter('tipo', event.target.value)}
            opciones={[
              { valor: '', texto: 'Todos' },
              ...tiposDocumento,
            ]}
          />
          <SelectField
            etiqueta="Ordenar por"
            value={order}
            onChange={(event) => filter('orden', event.target.value)}
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
            disabled={!operationPeriod || operation.isPending}
            onClick={() => operation.mutate('export')}
          >
            Exportar confirmados
          </Button>
          <Button
            disabled={!operationPeriod || operation.isPending}
            onClick={() => operation.mutate('reconcile')}
          >
            Buscar medios de pago
          </Button>
        </div>
      </Panel>
      <p role="status">{upload.isPending ? 'Cargando documentos…' : message}</p>
      {documents.error && <p role="alert">{documents.error.message}</p>}
      {batch.error && <p role="alert">{batch.error.message}</p>}
      {periods.error && <p role="alert">{periods.error.message}</p>}
      <Panel titulo={`Documentos (${documents.data?.total ?? 0})`}>
        {documents.isLoading && <p role="status">Cargando documentos…</p>}
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
                    doc.associated_payment?.channel ||
                      doc.extracted?.fields['payment.channel']?.value ||
                      doc.associated_payment?.method ||
                      valor(doc, 'payment.method'),
                    doc.associated_payment?.operation_number || valor(doc, 'payment.operation_number'),
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
        {!documents.isLoading && !documents.error && !documents.data?.items.length && (
          <p>No hay documentos con estos filtros.</p>
        )}
        <div className={layout.fila}>
          <Button disabled={page === 1 || documents.isLoading} onClick={() => filter('pagina', String(page - 1))}>
            Anterior
          </Button>
          <span>Página {page}</span>
          <Button
            disabled={documents.isLoading || page * 25 >= (documents.data?.total ?? 0)}
            onClick={() => filter('pagina', String(page + 1))}
          >
            Siguiente
          </Button>
        </div>
      </Panel>
    </div>
  );
}
