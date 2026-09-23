import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';
import type { FormEvent } from 'react';

import {
  corregirClasificacionFrecuente,
  eliminarClasificacionFrecuente,
  listarClasificacionesFrecuentes,
} from '@/api/clasificacion';
import { listarCuentas } from '@/api/planCuentas';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { SelectField, TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearEntero } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ClasificacionFrecuente, CuentaClasificada } from '@/types/api';
import type { Libro } from '@/types/domain';

const LIBROS = [
  { valor: '', texto: 'Compras y ventas' },
  { valor: 'compras', texto: 'Compras' },
  { valor: 'ventas', texto: 'Ventas' },
] as const;

function detalle(fallo: unknown): string {
  return fallo instanceof ApiError ? fallo.message : 'Error inesperado.';
}

function textoCuenta(cuenta: CuentaClasificada | null): string {
  if (!cuenta) return '—';
  return cuenta.descripcion ? `${cuenta.codigo} · ${cuenta.descripcion}` : cuenta.codigo;
}

function Estado({ entrada }: { entrada: ClasificacionFrecuente }) {
  if (entrada.origen === 'usuario') return <Badge tono="exito">Corregida por usuario</Badge>;
  if (entrada.confiable) return <Badge tono="info">IA · se reutiliza</Badge>;
  return <Badge tono="aviso">Requiere revisión</Badge>;
}

/** Formulario para fijar la cuenta de una clasificación frecuente. */
function DialogoCorregir({
  ruc,
  entrada,
  onCerrar,
}: {
  ruc: string;
  entrada: ClasificacionFrecuente;
  onCerrar: () => void;
}) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const idSugerencias = useId();
  const [codigo, setCodigo] = useState(entrada.cuenta_base?.codigo ?? '');
  const [descripcion, setDescripcion] = useState(entrada.cuenta_base?.descripcion ?? '');
  const [total, setTotal] = useState(entrada.cuenta_total?.codigo ?? '');

  // Sugerencias del maestro de cuentas de la empresa, si lo cargó.
  const busqueda = codigo.trim();
  const sugerencias = useQuery({
    queryKey: ['plan-cuentas', ruc, busqueda, 'sugerencias'],
    queryFn: () => listarCuentas(ruc, { busqueda, limit: 15 }),
    enabled: busqueda.length >= 2,
    staleTime: 60_000,
  });

  const guardar = useMutation({
    mutationFn: () =>
      corregirClasificacionFrecuente(
        ruc,
        entrada.id,
        { codigo: busqueda, descripcion: descripcion.trim() || null },
        total.trim()
          ? {
              codigo: total.trim(),
              descripcion:
                total.trim() === entrada.cuenta_total?.codigo
                  ? entrada.cuenta_total.descripcion
                  : null,
            }
          : null,
      ),
    onSuccess: async () => {
      mostrar({
        tono: 'exito',
        titulo: 'Clasificación guardada',
        detalle:
          'Se aplicó a los comprobantes que la usaban y se reutilizará en los siguientes.',
      });
      await cliente.invalidateQueries({ queryKey: ['clasificaciones-frecuentes', ruc] });
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc] });
      onCerrar();
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo guardar', detalle: detalle(fallo) }),
  });

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (busqueda) guardar.mutate();
  }

  function alCambiarCodigo(valor: string) {
    setCodigo(valor);
    // Al elegir una sugerencia del maestro se completa su descripción.
    const delMaestro = sugerencias.data?.cuentas.find((c) => c.cuenta === valor.trim());
    if (delMaestro) setDescripcion(delMaestro.descripcion);
  }

  return (
    <Dialog
      abierto
      titulo="Corregir clasificación"
      texto={entrada.glosa}
      onCerrar={onCerrar}
      acciones={
        <>
          <Button variante="fantasma" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form="form-corregir"
            variante="primario"
            cargando={guardar.isPending}
            disabled={!busqueda}
          >
            Guardar y aplicar
          </Button>
        </>
      }
    >
      <form id="form-corregir" className={layout.pila} onSubmit={alEnviar}>
        <TextField
          etiqueta="Cuenta base"
          value={codigo}
          onChange={(evento) => alCambiarCodigo(evento.target.value)}
          list={idSugerencias}
          inputMode="numeric"
          mono
          required
          ayuda="Escribe el código o parte de la descripción para ver sugerencias del maestro de cuentas."
        />
        <datalist id={idSugerencias}>
          {sugerencias.data?.cuentas.map((cuenta) => (
            <option key={cuenta.cuenta} value={cuenta.cuenta}>
              {cuenta.descripcion}
            </option>
          ))}
        </datalist>
        <TextField
          etiqueta="Descripción de la cuenta"
          value={descripcion}
          onChange={(evento) => setDescripcion(evento.target.value)}
          ayuda="Opcional: si la dejas vacía se toma del maestro de cuentas."
        />
        <TextField
          etiqueta="Cuenta total"
          value={total}
          onChange={(evento) => setTotal(evento.target.value)}
          inputMode="numeric"
          mono
          ayuda="Normalmente 4212 en compras y 1212 en ventas."
        />
      </form>
    </Dialog>
  );
}

/**
 * Clasificaciones frecuentes de la empresa: cada glosa distinta que ya pasó
 * por la IA, con la cuenta que se le dio. Las confiables se reutilizan sin
 * volver a consultar a la IA; aquí se corrigen las dudosas y las equivocadas.
 */
export function ClasificacionesPage() {
  useDocumentTitle('Clasificaciones frecuentes');
  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const [libro, setLibro] = useState<Libro | ''>('');
  const [editando, setEditando] = useState<ClasificacionFrecuente | null>(null);

  const entradas = useQuery({
    queryKey: ['clasificaciones-frecuentes', ruc, libro],
    queryFn: () => listarClasificacionesFrecuentes(ruc, libro || undefined),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => eliminarClasificacionFrecuente(ruc, id),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Clasificación olvidada' });
      await cliente.invalidateQueries({ queryKey: ['clasificaciones-frecuentes', ruc] });
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo eliminar', detalle: detalle(fallo) }),
  });

  const confirmar = useMutation({
    mutationFn: (entrada: ClasificacionFrecuente) =>
      corregirClasificacionFrecuente(
        ruc,
        entrada.id,
        entrada.cuenta_base as CuentaClasificada,
        entrada.cuenta_total,
      ),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Clasificación confirmada' });
      await cliente.invalidateQueries({ queryKey: ['clasificaciones-frecuentes', ruc] });
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc] });
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo confirmar', detalle: detalle(fallo) }),
  });

  const datos = entradas.data ?? [];
  const porRevisar = datos.filter((e) => !e.confiable).length;
  const reutilizaciones = datos.reduce((suma, e) => suma + e.usos, 0);

  const columnas: readonly Columna<ClasificacionFrecuente>[] = [
    {
      clave: 'glosa',
      cabecera: 'Glosa',
      cabeceraDeFila: true,
      anchoMinimo: '16rem',
      render: (fila) => fila.glosa,
    },
    { clave: 'libro', cabecera: 'Libro', render: (fila) => fila.libro },
    {
      clave: 'cuenta_base',
      cabecera: 'Cuenta base',
      anchoMinimo: '12rem',
      render: (fila) => textoCuenta(fila.cuenta_base),
    },
    {
      clave: 'cuenta_total',
      cabecera: 'Cuenta total',
      monoespaciada: true,
      render: (fila) => fila.cuenta_total?.codigo ?? '—',
    },
    {
      clave: 'usos',
      cabecera: 'Reutilizada',
      numerica: true,
      render: (fila) => formatearEntero(fila.usos),
    },
    { clave: 'estado', cabecera: 'Estado', render: (fila) => <Estado entrada={fila} /> },
    {
      clave: 'acciones',
      cabecera: 'Acciones',
      render: (fila) => (
        <div className={layout.fila}>
          <Button pequeno onClick={() => setEditando(fila)}>
            Corregir
          </Button>
          {fila.origen === 'ia' && fila.cuenta_base ? (
            <Button
              pequeno
              variante="fantasma"
              onClick={() => confirmar.mutate(fila)}
              disabled={confirmar.isPending}
              title="La cuenta es correcta: fijarla y reutilizarla"
            >
              Confirmar
            </Button>
          ) : null}
          <Button
            pequeno
            variante="fantasma"
            onClick={() => eliminar.mutate(fila.id)}
            disabled={eliminar.isPending}
            aria-label={`Olvidar la clasificación de ${fila.glosa}`}
          >
            Olvidar
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        titulo="Clasificaciones frecuentes"
        descripcion="Cada glosa ya clasificada y su cuenta. Si llega un comprobante con la misma glosa, se reutiliza sin consultar a la IA. Corrige aquí las que requieren revisión: el cambio se aplica a los comprobantes que la usaban."
        acciones={
          <SelectField
            etiqueta="Libro"
            value={libro}
            onChange={(evento) => setLibro(evento.target.value as Libro | '')}
            opciones={LIBROS}
          />
        }
      />

      <Panel
        titulo="Glosas clasificadas"
        descripcion={
          entradas.data
            ? `${formatearEntero(datos.length)} glosas · ${formatearEntero(porRevisar)} por revisar · ${formatearEntero(reutilizaciones)} comprobantes clasificados sin consultar a la IA`
            : undefined
        }
      >
        {entradas.isPending ? (
          <Skeleton lineas={5} etiqueta="Cargando las clasificaciones" />
        ) : null}
        {entradas.isError ? (
          <ErrorState
            titulo="No se pudieron cargar las clasificaciones"
            texto={detalle(entradas.error)}
            accion={
              <Button pequeno onClick={() => void entradas.refetch()}>
                Reintentar
              </Button>
            }
          />
        ) : null}
        {entradas.data ? (
          <DataTable
            leyenda="Clasificaciones frecuentes de la empresa"
            leyendaOculta
            columnas={columnas}
            filas={datos}
            claveDeFila={(fila) => fila.id}
            vacio={
              <EmptyState
                titulo="Aún no hay clasificaciones"
                texto="Se crean al clasificar comprobantes con glosa desde la pantalla de cada periodo."
              />
            }
          />
        ) : null}
      </Panel>

      {editando ? (
        <DialogoCorregir ruc={ruc} entrada={editando} onCerrar={() => setEditando(null)} />
      ) : null}
    </>
  );
}
