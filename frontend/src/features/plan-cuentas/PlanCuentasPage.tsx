import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

import { cargarCuentas, eliminarCuentas, listarCuentas } from '@/api/planCuentas';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { FileField, TextField } from '@/components/ui/Field';
import { Pagination } from '@/components/ui/Pagination';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { CuentaResponse } from '@/types/api';

const POR_PAGINA = 100;

/** Sangría por nivel: es lo único que dibuja la jerarquía del plan contable. */
const SANGRIA: Record<number, string> = { 1: '0', 2: '1rem', 3: '2rem' };

export function PlanCuentasPage() {
  useDocumentTitle('Maestro de cuentas');

  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const entradaArchivo = useRef<HTMLInputElement>(null);
  const [errorArchivo, setErrorArchivo] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState('');
  const [pagina, setPagina] = useState(1);
  const [confirmarBorrado, setConfirmarBorrado] = useState(false);

  const cuentas = useQuery({
    queryKey: ['plan-cuentas', ruc, busqueda, pagina],
    queryFn: () =>
      listarCuentas(ruc, {
        busqueda: busqueda || undefined,
        limit: POR_PAGINA,
        skip: (pagina - 1) * POR_PAGINA,
      }),
  });

  const cargar = useMutation({
    mutationFn: (archivo: File) => cargarCuentas(ruc, archivo),
    onSuccess: async (respuesta) => {
      mostrar({
        tono: 'exito',
        titulo: respuesta.mensaje,
        detalle: `${respuesta.cuentas} cuentas disponibles.`,
      });
      if (entradaArchivo.current) entradaArchivo.current.value = '';
      setPagina(1);
      await cliente.invalidateQueries({ queryKey: ['plan-cuentas', ruc] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo cargar el maestro',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const borrar = useMutation({
    mutationFn: () => eliminarCuentas(ruc),
    onSuccess: async (respuesta) => {
      mostrar({ tono: 'exito', titulo: respuesta.mensaje ?? 'Maestro borrado' });
      setConfirmarBorrado(false);
      setPagina(1);
      await cliente.invalidateQueries({ queryKey: ['plan-cuentas', ruc] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo borrar el maestro',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  function alElegir(evento: ChangeEvent<HTMLInputElement>) {
    const archivo = evento.target.files?.[0];
    if (!archivo) return;

    if (!/\.xlsx?$|\.xlsm$/i.test(archivo.name)) {
      setErrorArchivo('Solo se permiten archivos Excel (.xlsx o .xlsm).');
      return;
    }
    setErrorArchivo(null);
    cargar.mutate(archivo);
  }

  const total = cuentas.data?.total ?? 0;
  const filas = cuentas.data?.cuentas ?? [];
  const hayMaestro = total > 0 || busqueda !== '';
  const desde = total === 0 ? 0 : (pagina - 1) * POR_PAGINA + 1;

  const columnas: readonly Columna<CuentaResponse>[] = [
    {
      clave: 'cuenta',
      cabecera: 'Cuenta',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => (
        <span style={{ paddingInlineStart: SANGRIA[fila.nivel] ?? '0' }}>{fila.cuenta}</span>
      ),
    },
    {
      clave: 'descripcion',
      cabecera: 'Descripción',
      anchoMinimo: '24rem',
      render: (fila) => fila.descripcion,
    },
    { clave: 'tipo', cabecera: 'Tipo', render: (fila) => fila.tipo },
    { clave: 'analisis', cabecera: 'Análisis', render: (fila) => fila.analisis || '—' },
    {
      clave: 'centro_costos',
      cabecera: 'Centro de costos',
      anchoMinimo: '12rem',
      render: (fila) => fila.centro_costos || '—',
    },
  ];

  return (
    <>
      <PageHeader
        titulo="Maestro de cuentas"
        descripcion="El plan contable de la empresa, tal como lo exporta Contasis. Es el catálogo con el que se interpreta cada código de cuenta del registro."
        acciones={
          total > 0 ? (
            <Button variante="fantasma" onClick={() => setConfirmarBorrado(true)}>
              Borrar maestro
            </Button>
          ) : undefined
        }
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Cargar el maestro"
          descripcion="Se espera la hoja «PLAN DE CUENTAS» con las columnas CUENTA, DESCRIPCION, TIPO, ANALISIS y CENTRO DE COSTOS. Cargar reemplaza el maestro completo: el archivo es la fuente de verdad."
        >
          <FileField
            ref={entradaArchivo}
            etiqueta="Archivo Excel"
            name="archivo"
            accept=".xlsx,.xlsm"
            onChange={alElegir}
            disabled={cargar.isPending}
            error={errorArchivo}
            ayuda={cargar.isPending ? 'Leyendo las cuentas…' : 'Un archivo por vez.'}
          />
        </Panel>

        <Panel
          titulo="Cuentas cargadas"
          descripcion={
            total > 0
              ? 'La sangría del código refleja la jerarquía del archivo: elemento, cuenta y subcuenta.'
              : undefined
          }
        >
          <div className={layout.pila}>
            {hayMaestro ? (
              <TextField
                etiqueta="Buscar"
                name="busqueda"
                value={busqueda}
                onChange={(evento) => {
                  setBusqueda(evento.target.value);
                  setPagina(1);
                }}
                ayuda="Filtra por código o por descripción."
              />
            ) : null}

            {cuentas.isPending ? <Skeleton lineas={5} etiqueta="Cargando cuentas" /> : null}

            {cuentas.isError ? (
              <ErrorState
                titulo="No se pudieron cargar las cuentas"
                texto={
                  cuentas.error instanceof ApiError
                    ? cuentas.error.message
                    : 'Error inesperado.'
                }
                accion={
                  <Button pequeno onClick={() => void cuentas.refetch()}>
                    Reintentar
                  </Button>
                }
              />
            ) : null}

            {cuentas.data ? (
              <>
                <DataTable
                  leyenda="Cuentas del plan contable de la empresa"
                  leyendaOculta
                  columnas={columnas}
                  filas={filas}
                  claveDeFila={(fila) => fila.cuenta}
                  vacio={
                    busqueda ? (
                      <EmptyState
                        titulo="Ninguna cuenta coincide"
                        texto={`No hay cuentas que contengan «${busqueda}».`}
                      />
                    ) : (
                      <EmptyState
                        titulo="Todavía no hay maestro"
                        texto="Sube el Excel de Contasis para que la clasificación contable pueda apoyarse en el plan de cuentas de esta empresa."
                      />
                    )
                  }
                />

                {total > 0 ? (
                  <TableFooter
                    recuento={`Mostrando ${desde}–${desde + filas.length - 1} de ${total} cuentas`}
                  >
                    <Pagination
                      pagina={pagina}
                      haySiguiente={pagina * POR_PAGINA < total}
                      onCambiar={setPagina}
                    />
                  </TableFooter>
                ) : null}
              </>
            ) : null}
          </div>
        </Panel>
      </div>

      <Dialog
        abierto={confirmarBorrado}
        titulo="¿Borrar el maestro de cuentas?"
        texto="Se eliminarán todas las cuentas cargadas para esta empresa. La clasificación contable dejará de apoyarse en el plan propio y volverá a usar solo la base de conocimiento general."
        onCerrar={() => setConfirmarBorrado(false)}
        acciones={
          <>
            <Button variante="fantasma" onClick={() => setConfirmarBorrado(false)}>
              Cancelar
            </Button>
            <Button
              variante="peligro"
              cargando={borrar.isPending}
              onClick={() => borrar.mutate()}
            >
              Borrar maestro
            </Button>
          </>
        }
      />
    </>
  );
}
