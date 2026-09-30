import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import { asociarVoucher, listarVouchers } from '@/api/vouchers';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useToast } from '@/hooks/useToast';
import { formatearFecha, formatearMoneda, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { PagoVoucher, VoucherPeriodo } from '@/types/api';
import type { Libro } from '@/types/domain';

import { presentarPago } from './pagoVoucher';
import { Dato, Seccion } from './Seccion';
import estilos from './Vouchers.module.css';

function monto(pago: { total: string | null; moneda: string }): string {
  return pago.total == null ? '—' : formatearMoneda(Number(pago.total), pago.moneda);
}

/** Celda «Pago» del listado: los vouchers que pagan el comprobante. */
export function PagoCelda({ pagos }: { pagos: readonly PagoVoucher[] | undefined }) {
  if (!pagos?.length) return <>—</>;
  return (
    <div className={estilos.pagos}>
      {pagos.map((pago) => (
        <span key={pago.id}>{presentarPago(pago)}</span>
      ))}
    </div>
  );
}

/** Lo que cambia al asociar o desasociar un voucher. */
function useAsociar(ruc: string, periodo: string, alTerminar?: () => void) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  return useMutation({
    mutationFn: ({
      id,
      serieNumero,
      periodoComprobante,
    }: {
      id: string;
      serieNumero: string | null;
      periodoComprobante?: string;
    }) => asociarVoucher(ruc, periodo, id, serieNumero, periodoComprobante),
    onSuccess: async (pago) => {
      mostrar({
        tono: 'exito',
        titulo: pago.serie_numero
          ? `${presentarPago(pago)} quedó como pago de ${pago.serie_numero}${
              pago.periodo_comprobante && pago.periodo_comprobante !== pago.periodo
                ? ` (${formatearPeriodo(pago.periodo_comprobante)})`
                : ''
            }`
          : `${presentarPago(pago)} quedó sin comprobante`,
      });
      alTerminar?.();
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
      await cliente.invalidateQueries({ queryKey: ['comprobante', ruc, periodo] });
      await cliente.invalidateQueries({ queryKey: ['comprobantes-externos', ruc] });
    },
    onError: (fallo) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo cambiar el voucher',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      }),
  });
}

function AsociarDialog({
  ruc,
  periodo,
  voucher,
  onCerrar,
}: {
  ruc: string;
  periodo: string;
  voucher: VoucherPeriodo | null;
  onCerrar: () => void;
}) {
  const [serieNumero, setSerieNumero] = useState('');
  const asociar = useAsociar(ruc, periodo, () => {
    setSerieNumero('');
    onCerrar();
  });

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const valor = serieNumero.trim().toUpperCase();
    if (voucher && valor) asociar.mutate({ id: voucher.id, serieNumero: valor });
  }

  return (
    <Dialog
      abierto={voucher !== null}
      titulo={voucher ? `Asociar ${presentarPago(voucher)}` : 'Asociar voucher'}
      texto={
        voucher
          ? `${formatearFecha(voucher.fecha)} · ${monto(voucher)}${voucher.contraparte ? ` · ${voucher.contraparte}` : ''}`
          : undefined
      }
      onCerrar={onCerrar}
      acciones={<Button onClick={onCerrar}>Cancelar</Button>}
    >
      {voucher ? (
        <>
          {voucher.candidatas.length > 0 ? (
            <Seccion titulo="Comprobantes con el mismo monto, de este periodo o del anterior">
              <ul className={estilos.candidatas}>
                {voucher.candidatas.map((candidata) => (
                  <li
                    key={`${candidata.periodo}:${candidata.serie_numero}`}
                    className={estilos.candidata}
                  >
                    <span>
                      <strong className={estilos.mono}>{candidata.serie_numero}</strong>
                      {' · '}
                      {candidata.razon_social || 'Sin contraparte'}
                      {' · '}
                      {formatearFecha(candidata.fecha_emision)}
                      {candidata.periodo !== voucher.periodo ? (
                        <>
                          {' · '}
                          <Badge tono="neutro">{formatearPeriodo(candidata.periodo)}</Badge>
                        </>
                      ) : null}
                    </span>
                    <Button
                      pequeno
                      aria-label={`Asociar a ${candidata.serie_numero} de ${formatearPeriodo(candidata.periodo)}`}
                      disabled={asociar.isPending}
                      onClick={() =>
                        asociar.mutate({
                          id: voucher.id,
                          serieNumero: candidata.serie_numero,
                          periodoComprobante: candidata.periodo,
                        })
                      }
                    >
                      Asociar
                    </Button>
                  </li>
                ))}
              </ul>
            </Seccion>
          ) : (
            <p className={layout.textoSecundario}>
              Ningún comprobante de este periodo ni del anterior tiene el mismo monto y moneda.
            </p>
          )}
          <Seccion titulo="Otro comprobante">
            <form className={estilos.formulario} onSubmit={alEnviar}>
              <TextField
                etiqueta="Serie-número"
                ayuda="Tal como sale en el listado, p. ej. B001-45. Se busca en este periodo y luego en el anterior."
                mono
                value={serieNumero}
                onChange={(evento) => setSerieNumero(evento.target.value)}
              />
              <Button type="submit" disabled={asociar.isPending || !serieNumero.trim()}>
                Asociar
              </Button>
            </form>
          </Seccion>
        </>
      ) : null}
    </Dialog>
  );
}

/**
 * Los vouchers de Apaclla Bot del periodo que todavía no están asociados al
 * comprobante que pagan. No aparece si no hay ninguno.
 */
export function VouchersSinComprobantePanel({
  ruc,
  periodo,
  libro,
}: {
  ruc: string;
  periodo: string;
  libro: Libro;
}) {
  const [abierto, setAbierto] = useState<VoucherPeriodo | null>(null);
  const consulta = useQuery({
    queryKey: ['comprobantes', ruc, periodo, libro, 'vouchers'],
    queryFn: () => listarVouchers(ruc, periodo, libro),
  });
  const sueltos = (consulta.data ?? []).filter((voucher) => !voucher.serie_numero);
  if (sueltos.length === 0) return null;

  const columnas: Columna<VoucherPeriodo>[] = [
    {
      clave: 'medio',
      cabecera: 'Medio de pago',
      render: (fila) => <Badge tono="info">{fila.medio_pago}</Badge>,
    },
    {
      clave: 'operacion',
      cabecera: 'N.º de operación',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => fila.nro_operacion,
    },
    { clave: 'fecha', cabecera: 'Fecha', render: (fila) => formatearFecha(fila.fecha) },
    {
      clave: 'contraparte',
      cabecera: libro === 'ventas' ? 'Cliente' : 'Proveedor',
      render: (fila) => fila.contraparte || '—',
    },
    { clave: 'total', cabecera: 'Total', numerica: true, render: (fila) => monto(fila) },
    {
      clave: 'accion',
      cabecera: 'Acción',
      render: (fila) => (
        <Button pequeno onClick={() => setAbierto(fila)}>
          Asociar
        </Button>
      ),
    },
  ];

  return (
    <Panel
      titulo={`Vouchers sin comprobante (${sueltos.length})`}
      descripcion="Yape, Plin y demás pagos de este periodo que llegaron desde Apaclla Bot y no se pudieron asociar solos: ningún comprobante de este periodo ni del anterior coincide, o coincide más de uno. En la plantilla salen en una hoja aparte hasta que los asocies."
    >
      <DataTable
        leyenda="Vouchers sin comprobante"
        leyendaOculta
        columnas={columnas}
        filas={sueltos}
        claveDeFila={(fila) => fila.id}
      />
      <AsociarDialog
        ruc={ruc}
        periodo={periodo}
        voucher={abierto}
        onCerrar={() => setAbierto(null)}
      />
    </Panel>
  );
}

/** Sección «Pagos» de la ficha del comprobante. */
export function SeccionPagos({
  ruc,
  periodo,
  pagos,
}: {
  ruc: string;
  periodo: string;
  pagos: readonly PagoVoucher[] | undefined;
}) {
  const desasociar = useAsociar(ruc, periodo);
  if (!pagos?.length) return null;
  return (
    <Seccion titulo="Pagos">
      <ul className={estilos.candidatas}>
        {pagos.map((pago) => (
          <li key={pago.id} className={estilos.candidata}>
            <dl className={layout.definiciones}>
              <Dato termino="Medio de pago">{pago.medio_pago}</Dato>
              <Dato termino="N.º de operación">
                <span className={estilos.mono}>{pago.nro_operacion}</span>
              </Dato>
              <Dato termino="Fecha">
                {formatearFecha(pago.fecha)}
                {pago.periodo !== periodo
                  ? ` · voucher de ${formatearPeriodo(pago.periodo)}`
                  : ''}
              </Dato>
              <Dato termino="Monto">{monto(pago)}</Dato>
              <Dato termino="Asociado">
                {pago.asociacion === 'manual' ? 'A mano' : 'Automáticamente'}
              </Dato>
            </dl>
            <Button
              pequeno
              disabled={desasociar.isPending}
              onClick={() => desasociar.mutate({ id: pago.id, serieNumero: null })}
            >
              Desasociar
            </Button>
          </li>
        ))}
      </ul>
    </Seccion>
  );
}
