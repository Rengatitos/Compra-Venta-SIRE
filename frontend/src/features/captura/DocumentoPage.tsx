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
import { TextField, TextAreaField, SelectField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import layout from '@/styles/layouts.module.css';
import styles from './Inventario.module.css';
import { tiposDocumento } from './catalogo';

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
  'customer.document_number': 'Documento del cliente',
  'service.description': 'Concepto / glosa',
  'vehicle.plate': 'Placa',
  'amounts.subtotal': 'Subtotal',
  'amounts.taxable': 'Base imponible',
  'amounts.exempt': 'Importe exonerado',
  'amounts.unaffected': 'Importe inafecto',
  'amounts.igv': 'IGV',
  'amounts.total': 'Total',
  'payment.method': 'Forma de pago',
  'payment.channel': 'Canal',
  'payment.operation_number': 'Número de operación',
  'honorarios.gross': 'Honorarios brutos',
  'honorarios.retention': 'Retención de honorarios',
  'honorarios.net': 'Honorarios netos',
};

const extraLabels: Record<string, string> = {
  'issuer.document_type': 'Tipo de documento del emisor',
  'issuer.document_number': 'Documento del emisor',
  'issuer.address': 'Dirección del emisor',
  'customer.document_type': 'Tipo de documento del cliente',
  'customer.address': 'Dirección del cliente',
  'document.issue_time': 'Hora de emisión',
  'amounts.discount': 'Descuento',
  'amounts.other_taxes': 'Otros tributos',
  'payment.destination_channel': 'Canal de destino',
  'payment.authorization_number': 'Código de autorización',
  'payment.reference': 'Referencia del pago',
  'payment.card_brand': 'Marca de tarjeta',
  'payment.card_last4': 'Últimos cuatro dígitos de tarjeta',
  'payment.recipient': 'Destinatario del pago',
  'payment.bank': 'Banco',
  'payment.phone': 'Teléfono del pago',
  'payment.processor': 'Procesador del pago',
  'payment.merchant': 'Comercio',
  'payment.terminal': 'Terminal',
  'payment.transaction_status': 'Estado de la transacción',
  'payment.contactless': 'Pago sin contacto',
  'service.provider': 'Empresa de servicio',
  'service.type': 'Tipo de servicio',
  'service.customer_code': 'Código de cliente o suministro',
  'service.holder': 'Titular del servicio',
  'service.billing_period': 'Periodo facturado',
  'service.due_date': 'Vencimiento del servicio',
  'service.consumption': 'Consumo',
  'vehicle.odometer': 'Kilometraje',
  'references.document_type': 'Tipo de documento de referencia',
  'references.series': 'Serie de referencia',
  'references.number': 'Número de referencia',
  'references.reason': 'Motivo de modificación',
  'transport.date': 'Fecha de traslado',
  'transport.origin': 'Punto de partida',
  'transport.destination': 'Punto de llegada',
  'transport.carrier': 'Transportista',
  'transport.carrier_ruc': 'RUC del transportista',
  'transport.license': 'Licencia de conducir',
  'transport.weight': 'Peso',
  'transport.packages': 'Bultos',
};

function Editor({ doc }: { doc: Documento }) {
  const ruc = useRuc();
  const client = useQueryClient();
  const [fields, setFields] = useState<Record<string, string | null>>({});
  const [kind, setKind] = useState(doc.document_type ?? 'UNKNOWN');
  const [period, setPeriod] = useState(doc.accounting_period ?? '');
  const [note, setNote] = useState('');
  const linked = Boolean(doc.associated_payment || doc.tax_document_id);
  const dirty = kind !== (doc.document_type ?? 'UNKNOWN') || Object.entries(fields).some(
    ([key, value]) => value !== (doc.extracted?.fields[key]?.value ?? null),
  );
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
    linked ||
    ['CONFIRMED', 'EXPORTED', 'QUEUED', 'OCR_PROCESSING', 'FAILED', 'CANCELLED'].includes(
      doc.status,
    );
  return (
    <div className={layout.pila}>
      <p>
        Estado: {doc.status} · Periodo: {doc.accounting_period ?? 'Sin asignar'}
      </p>
      <p>Fecha de ingreso: {new Date(doc.received_at).toLocaleString('es-PE')}</p>
      {linked && <p>Este documento está vinculado. Sus datos están bloqueados para conservar la conciliación.</p>}
      {dirty && <p role="status">Guarda las correcciones antes de revisar o confirmar el documento.</p>}
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
        <SelectField
          etiqueta="Tipo de documento"
          value={kind}
          disabled={locked}
          opciones={tiposDocumento}
          onChange={(event) => setKind(event.target.value)}
        />
        <div className={layout.rejillaFormulario}>
          {Object.entries(labels).filter(([key]) => key in (doc.extracted?.fields ?? {})).map(([key, label]) => (
            <TextField
              key={key}
              etiqueta={label}
              type={key === 'document.issue_date' ? 'date' : 'text'}
              disabled={locked}
              maxLength={1000}
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
        <details>
          <summary>Corregir otros campos extraídos</summary>
          <div className={layout.rejillaFormulario}>
            {Object.keys(doc.extracted?.fields ?? {}).filter((key) => !(key in labels)).map((key) => (
              <TextField
                key={key}
                etiqueta={extraLabels[key] ?? key}
                disabled={locked}
                maxLength={1000}
                value={fields[key] !== undefined ? (fields[key] ?? '') : (doc.extracted?.fields[key]?.value ?? '')}
                ayuda={doc.extracted?.fields[key]?.status}
                onChange={(event) => setFields({ ...fields, [key]: event.target.value || null })}
              />
            ))}
          </div>
        </details>
        <Button type="submit" disabled={locked || !dirty}>
          Guardar correcciones
        </Button>
      </form>
      <Panel titulo="Resolver periodo y observaciones">
        <TextField
          etiqueta="Periodo contable (YYYYMM)"
          value={period}
          inputMode="numeric"
          maxLength={6}
          onChange={(event) => setPeriod(event.target.value)}
          disabled={locked}
        />
        <TextAreaField
          etiqueta="Motivo de la revisión"
          value={note}
          maxLength={500}
          disabled={locked}
          onChange={(event) => setNote(event.target.value)}
        />
        <div className={layout.fila}>
          <Button disabled={locked || dirty || !/^\d{4}(0[1-9]|1[0-2])$/.test(period)} onClick={() => mutation.mutate('move-period')}>
            Asignar este periodo
          </Button>
          <Button disabled={locked || dirty || !note.trim()} onClick={() => mutation.mutate('resolve')}>
            Marcar revisado
          </Button>
          <Button
            disabled={mutation.isPending || dirty || doc.status !== 'READY'}
            onClick={() => mutation.mutate('confirm')}
          >
            Confirmar
          </Button>
          <Button
            disabled={
              mutation.isPending ||
              dirty || linked ||
              ['CONFIRMED', 'EXPORTED', 'QUEUED', 'OCR_PROCESSING', 'CANCELLED'].includes(doc.status)
            }
            onClick={() => mutation.mutate('reprocess')}
          >
            Reprocesar OCR
          </Button>
          <Button
            variante="peligro"
            disabled={
              mutation.isPending ||
              dirty || linked ||
              ['QUEUED', 'OCR_PROCESSING', 'CANCELLED', 'CONFIRMED', 'EXPORTED'].includes(doc.status)
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
              <dt>{labels[key] ?? extraLabels[key] ?? key}</dt>
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
      {query.isLoading && <p role="status">Cargando comprobante…</p>}
      {query.data && (
        <>
          <div className={styles.detalle}>
            <Panel titulo="Archivo original">
              <Original key={`${id}-${query.data.mime ?? ''}`} id={id} mime={query.data.mime} />
            </Panel>
            <Panel titulo="Datos extraídos">
              <Editor key={`${query.data.id}-${query.data.revision}`} doc={query.data} />
            </Panel>
          </div>
          <Panel titulo="Medios de pago sugeridos">
            {query.data.associated_payment && (
              <p>
                Pago vinculado: {query.data.associated_payment.channel || query.data.associated_payment.method || 'Sin canal'}
                {' · '}Operación: {query.data.associated_payment.operation_number ?? 'Sin número'}{' · '}
                <Link to={`/comprobantes/${query.data.associated_payment.document_id}`}>Ver pago vinculado</Link>
              </p>
            )}
            {query.data.tax_document_id && (
              <p><Link to={`/comprobantes/${query.data.tax_document_id}`}>Ver comprobante vinculado</Link></p>
            )}
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
                    disabled={reconcile.isPending || !['READY', 'CONFIRMED'].includes(query.data?.status ?? '') || Boolean(query.data?.associated_payment || query.data?.tax_document_id)}
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
