import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';

import {
  accionDocumento,
  archivoDocumento,
  editarDocumento,
  obtenerDocumento,
  confirmarCoincidencia,
} from '@/api/captura';
import type { Documento } from '@/api/captura';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { TextField, TextAreaField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import layout from '@/styles/layouts.module.css';
import styles from './Inventario.module.css';

function Original({ id, mime }: { id: string; mime?: string }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    let objectUrl = '';
    void archivoDocumento(id)
      .then((blob) => {
        if (active) {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      })
      .catch((reason: unknown) => {
        if (active)
          setError(reason instanceof Error ? reason.message : 'No se pudo abrir el archivo.');
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id]);
  if (error) return <p role="alert">{error}</p>;
  if (!url) return <p>Cargando original…</p>;
  return mime === 'application/pdf' ? (
    <iframe title="Comprobante original" src={url} className={styles.original} />
  ) : (
    <img
      alt="Comprobante original enviado por el cliente"
      src={url}
      className={styles.original}
    />
  );
}

const labels: Record<string, string> = {
  'document.issue_date': 'Fecha del comprobante',
  'document.series': 'Serie',
  'document.number': 'Número',
  'document.currency': 'Moneda',
  'issuer.ruc': 'RUC emisor',
  'issuer.name': 'Proveedor',
  'customer.name': 'Cliente',
  'service.description': 'Concepto / glosa',
  'vehicle.plate': 'Placa',
  'amounts.subtotal': 'Subtotal',
  'amounts.igv': 'IGV',
  'amounts.total': 'Total',
  'payment.method': 'Forma de pago',
  'payment.channel': 'Canal',
  'payment.operation_number': 'Número de operación',
};

function Editor({ doc }: { doc: Documento }) {
  const ruc = useRuc();
  const client = useQueryClient();
  const [fields, setFields] = useState<Record<string, string | null>>({});
  const [kind, setKind] = useState(doc.document_type ?? 'UNKNOWN');
  const [period, setPeriod] = useState(doc.accounting_period ?? '');
  const [note, setNote] = useState('');
  const mutation = useMutation({
    mutationFn: (action: string) =>
      action === 'edit'
        ? editarDocumento(doc, fields, kind)
        : accionDocumento(doc, action, { accounting_period: period, note }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['captura', ruc] });
    },
  });
  const locked =
    mutation.isPending ||
    ['CONFIRMED', 'EXPORTED', 'QUEUED', 'OCR_PROCESSING', 'FAILED', 'CANCELLED'].includes(
      doc.status,
    );
  return (
    <div className={layout.pila}>
      <p>
        Estado: {doc.status} · Periodo: {doc.accounting_period ?? 'Sin asignar'}
      </p>
      <p>Fecha de ingreso: {new Date(doc.received_at).toLocaleString('es-PE')}</p>
      {doc.issues.length > 0 && (
        <div className={styles.observacion}>
          <strong>Requiere revisión</strong>
          <ul>
            {doc.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      )}
      {mutation.error && <p role="alert">{mutation.error.message}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate('edit');
        }}
      >
        <TextField
          etiqueta="Tipo de documento"
          value={kind}
          disabled={locked}
          onChange={(event) => setKind(event.target.value)}
        />
        <div className={layout.rejillaFormulario}>
          {Object.entries(labels).map(([key, label]) => (
            <TextField
              key={key}
              etiqueta={label}
              type={key === 'document.issue_date' ? 'date' : 'text'}
              disabled={locked}
              value={
                fields[key] !== undefined
                  ? (fields[key] ?? '')
                  : (doc.extracted?.fields[key]?.value ?? '')
              }
              ayuda={doc.extracted?.fields[key]?.status}
              onChange={(event) => setFields({ ...fields, [key]: event.target.value || null })}
            />
          ))}
        </div>
        <Button type="submit" disabled={locked}>
          Guardar correcciones
        </Button>
      </form>
      <Panel titulo="Resolver periodo y observaciones">
        <TextField
          etiqueta="Periodo contable (YYYYMM)"
          value={period}
          onChange={(event) => setPeriod(event.target.value)}
          disabled={locked}
        />
        <TextAreaField
          etiqueta="Motivo de la revisión"
          value={note}
          disabled={locked}
          onChange={(event) => setNote(event.target.value)}
        />
        <div className={layout.fila}>
          <Button disabled={locked || !period} onClick={() => mutation.mutate('move-period')}>
            Asignar este periodo
          </Button>
          <Button disabled={locked || !note.trim()} onClick={() => mutation.mutate('resolve')}>
            Marcar revisado
          </Button>
          <Button
            disabled={mutation.isPending || doc.status !== 'READY'}
            onClick={() => mutation.mutate('confirm')}
          >
            Confirmar
          </Button>
          <Button
            disabled={
              mutation.isPending ||
              ['CONFIRMED', 'QUEUED', 'OCR_PROCESSING'].includes(doc.status)
            }
            onClick={() => mutation.mutate('reprocess')}
          >
            Reprocesar OCR
          </Button>
          <Button
            variante="peligro"
            disabled={
              mutation.isPending ||
              ['QUEUED', 'OCR_PROCESSING', 'CANCELLED', 'CONFIRMED'].includes(doc.status)
            }
            onClick={() => mutation.mutate('cancel')}
          >
            Excluir
          </Button>
        </div>
      </Panel>
      <details>
        <summary>Todos los campos y evidencia</summary>
        <dl>
          {Object.entries(doc.extracted?.fields ?? {}).map(([key, field]) => (
            <div key={key}>
              <dt>{labels[key] ?? key}</dt>
              <dd>
                {field.value ?? 'Sin valor'} · {field.status} ·{' '}
                {Math.round(field.confidence * 100)}% · {field.source}
                {field.raw_text && <blockquote>{field.raw_text}</blockquote>}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}

export function DocumentoPage() {
  const { id = '' } = useParams();
  const ruc = useRuc();
  const client = useQueryClient();
  const reconcile = useMutation({
    mutationFn: confirmarCoincidencia,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['captura', ruc] });
    },
  });
  const query = useQuery({
    queryKey: ['captura', ruc, 'document', id],
    queryFn: () => obtenerDocumento(id),
    refetchInterval: (state) =>
      ['QUEUED', 'OCR_PROCESSING'].includes(state.state.data?.status ?? '') ? 5000 : false,
  });
  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Revisar comprobante"
        acciones={<Link to="/comprobantes">Volver al inventario</Link>}
      />
      {query.error && <p role="alert">{query.error.message}</p>}
      {query.data && (
        <>
          <div className={styles.detalle}>
            <Panel titulo="Archivo original">
              <Original key={`${id}-${query.data.mime ?? ''}`} id={id} mime={query.data.mime} />
            </Panel>
            <Panel titulo="Datos extraídos">
              <Editor key={query.data.revision} doc={query.data} />
            </Panel>
          </div>
          <Panel titulo="Medios de pago sugeridos">
            {reconcile.error && <p role="alert">{reconcile.error.message}</p>}
            {!query.data.matches?.length && <p>No hay coincidencias sugeridas.</p>}
            {query.data.matches?.map((match) => (
              <div key={match.id}>
                Coincidencia {match.score}% · {match.status} ·{' '}
                {match.documents
                  .filter((other) => other !== id)
                  .map((other) => (
                    <Link key={other} to={`/comprobantes/${other}`}>
                      Ver documento relacionado
                    </Link>
                  ))}
                {match.status === 'SUGGESTED' && (
                  <Button
                    disabled={reconcile.isPending}
                    onClick={() => reconcile.mutate(match.id)}
                  >
                    Vincular pago
                  </Button>
                )}
              </div>
            ))}
          </Panel>
          <Panel titulo="Historial de cambios">
            <ul>
              {query.data.audit?.map((entry) => (
                <li key={entry.id}>
                  {new Date(entry.timestamp).toLocaleString('es-PE')} · {entry.action} ·{' '}
                  {entry.actor}
                </li>
              ))}
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}
