import { descargar, enviarFormulario, obtenerArchivo, pedir, segmento } from '@/lib/http';
import type { Consulta } from '@/lib/http';

export interface Campo {
  value: string | null;
  status: string;
  confidence: number;
  source: string;
  raw_text?: string | null;
}
export interface Documento {
  id: string;
  revision: number;
  status: string;
  document_type?: string;
  document_date: string | null;
  received_at: string;
  accounting_period: string | null;
  period_validation: string;
  source: string;
  batch_id: string | null;
  sunat_code?: string | null;
  mime?: string;
  issues: string[];
  tax_document_id?: string | null;
  associated_payment?: {
    document_id: string;
    channel: string | null;
    method: string | null;
    operation_number: string | null;
  };
  extracted?: { fields: Record<string, Campo> };
  audit?: { id: string; action: string; timestamp: string; actor: string }[];
  matches?: { id: string; documents: string[]; score: number; status: string }[];
}
export interface Lote {
  id: string;
  accounting_period: string;
  status: string;
  received_count: number;
  created_at: string;
  counts?: Record<string, number>;
}
const base = '/captura';
export const confirmarCoincidencia = (id: string) =>
  pedir(`${base}/reconciliation/${segmento(id)}/confirm`, { metodo: 'POST' });
export const listarDocumentos = (consulta: Consulta) =>
  pedir<{ items: Documento[]; total: number; page: number }>(`${base}/documents`, { consulta });
export const obtenerDocumento = (id: string) =>
  pedir<Documento>(`${base}/documents/${segmento(id)}`);
export const listarPeriodosCaptura = () =>
  pedir<{ _id: string | null; count: number }[]>(`${base}/periods`);
export const resumenPeriodoCaptura = (period: string) =>
  pedir<{ _id: { type: string | null; status: string }; count: number }[]>(
    `${base}/periods/${segmento(period.slice(0, 4))}/${segmento(period.slice(4))}/summary`,
  );
export const listarLotes = (page: number) =>
  pedir<Lote[]>(`${base}/batches`, { consulta: { page } });
export const obtenerLote = (id: string) => pedir<Lote>(`${base}/batches/${segmento(id)}`);
export const crearLote = (accounting_period: string) =>
  pedir<Lote>(`${base}/batches`, {
    metodo: 'POST',
    cuerpo: { accounting_period },
  });
export const accionLote = (id: string, action: 'close' | 'confirm') =>
  pedir<{ message?: string }>(`${base}/batches/${segmento(id)}/${action}`, { metodo: 'POST' });
export const accionDocumento = (
  doc: Documento,
  action: string,
  extra: Record<string, unknown> = {},
) =>
  pedir<Documento>(`${base}/documents/${segmento(doc.id)}/${action}`, {
    metodo: 'POST',
    cuerpo: { revision: doc.revision, ...extra },
  });
export const editarDocumento = (
  doc: Documento,
  fields: Record<string, string | null>,
  kind: string,
) =>
  pedir<Documento>(`${base}/documents/${segmento(doc.id)}`, {
    metodo: 'PATCH',
    cuerpo: { revision: doc.revision, fields, document_type: kind },
  });
export const cargarDocumento = (file: File, batchId?: string) => {
  const form = new FormData();
  form.append('file', file);
  if (batchId) form.append('batch_id', batchId);
  return enviarFormulario<Documento>(`${base}/documents`, form);
};
export const archivoDocumento = (id: string) =>
  obtenerArchivo(`${base}/documents/${segmento(id)}/file`);
export const exportarInventario = (period: string) =>
  descargar(`${base}/export`, 'inventario.csv', { period });
export const conciliarPeriodo = (accounting_period: string) =>
  pedir<{ suggested: number }>(`${base}/reconciliation/run`, {
    metodo: 'POST',
    cuerpo: { accounting_period },
  });
export const listarTelefonos = () =>
  pedir<{ phone: string; active: boolean }[]>(`${base}/phones`);
export const autorizarTelefono = (phone: string, active = true) =>
  pedir(`${base}/phones`, {
    metodo: 'POST',
    cuerpo: { phone, active },
  });
