import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router';

import { crearPeriodo, eliminarPeriodo, listarPeriodos } from '@/api/periodos';
import { sincronizarPropuesta } from '@/api/propuesta';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { CampoAccion, TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearPeriodo, periodoPorDefecto } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { PeriodoResponse } from '@/types/api';
import { esPeriodoValido } from '@/types/domain';

import { presentarEstadoPeriodo } from './estadoPeriodo';

export function PeriodosPage() {
  useDocumentTitle('Periodos');

  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [nuevoPeriodo, setNuevoPeriodo] = useState(() => periodoPorDefecto());
  const [errorPeriodo, setErrorPeriodo] = useState<string | null>(null);
  const [aEliminar, setAEliminar] = useState<PeriodoResponse | null>(null);
  const [sincronizando, setSincronizando] = useState<string | null>(null);

  const periodos = useQuery({
    queryKey: ['periodos', ruc],
    queryFn: () => listarPeriodos(ruc),
  });

  function invalidarPeriodos() {
    return cliente.invalidateQueries({ queryKey: ['periodos', ruc] });
  }

  const crear = useMutation({
    mutationFn: (periodo: string) => crearPeriodo(ruc, periodo),
    onSuccess: async (creado) => {
      mostrar({
        tono: 'exito',
        titulo: `Periodo ${formatearPeriodo(creado.periodo)} creado`,
        detalle: 'Ya puedes sincronizar su propuesta de compras.',
      });
      await invalidarPeriodos();
    },
    onError: (fallo) => {
      setErrorPeriodo(
        fallo instanceof ApiError && fallo.esConflicto
          ? 'Ese periodo ya existe para esta empresa.'
          : fallo instanceof ApiError
            ? fallo.message
            : 'No se pudo crear el periodo.',
      );
    },
  });

  const sincronizar = useMutation({
    // Solo compras: `libro=ventas` responde 501 porque el RVIE no tiene cliente.
    mutationFn: (periodo: string) => sincronizarPropuesta(ruc, periodo, 'compras'),
    onMutate: (periodo) => setSincronizando(periodo),
    onSettled: () => setSincronizando(null),
    onSuccess: async (respuesta) => {
      const datos = respuesta.datos;
      const detalle = datos
        ? `${datos.nuevos} nuevos · ${datos.actualizados} actualizados · ${datos.descartados} descartados (series distintas de F o E, o fuera del periodo).`
        : undefined;
      mostrar({
        tono: 'exito',
        titulo: respuesta.mensaje ?? 'Sincronización completada',
        detalle,
      });
      await invalidarPeriodos();
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo sincronizar la propuesta',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const borrar = useMutation({
    mutationFn: (periodo: string) => eliminarPeriodo(ruc, periodo),
    onSuccess: async (_respuesta, periodo) => {
      mostrar({
        tono: 'exito',
        titulo: `Periodo ${formatearPeriodo(periodo)} eliminado`,
        detalle: 'También se borraron sus comprobantes.',
      });
      setAEliminar(null);
      await invalidarPeriodos();
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo eliminar el periodo',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  function alCrear(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const valor = nuevoPeriodo.trim();
    if (!esPeriodoValido(valor)) {
      setErrorPeriodo('El periodo debe tener el formato YYYYMM, por ejemplo 202606.');
      return;
    }
    setErrorPeriodo(null);
    crear.mutate(valor);
  }

  const columnas: readonly Columna<PeriodoResponse>[] = [
    {
      clave: 'periodo',
      cabecera: 'Periodo',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => (
        <Link to={`/periodos/${encodeURIComponent(fila.periodo)}`}>
          {formatearPeriodo(fila.periodo)}
        </Link>
      ),
    },
    {
      clave: 'codigo',
      cabecera: 'Código',
      monoespaciada: true,
      render: (fila) => fila.periodo,
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (fila) => {
        const presentacion = presentarEstadoPeriodo(fila.estado);
        return (
          <>
            <Badge tono={presentacion.tono} conPunto>
              {presentacion.texto}
            </Badge>
            <span className="visually-hidden">. {presentacion.detalle}</span>
          </>
        );
      },
    },
    {
      clave: 'acciones',
      cabecera: 'Acciones',
      render: (fila) => (
        <div className={layout.fila}>
          <Button
            pequeno
            onClick={() => sincronizar.mutate(fila.periodo)}
            cargando={sincronizando === fila.periodo}
          >
            Sincronizar compras
          </Button>
          <Button pequeno variante="fantasma" onClick={() => setAEliminar(fila)}>
            Eliminar
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        titulo="Periodos fiscales"
        descripcion="Crea el periodo, sincroniza su propuesta de compras desde el SIRE y entra a revisar los comprobantes."
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Crear periodo"
          descripcion="El formato es YYYYMM: cuatro dígitos de año y dos de mes."
        >
          <form className={layout.rejillaFormulario} onSubmit={alCrear} noValidate>
            <TextField
              etiqueta="Periodo"
              name="periodo"
              value={nuevoPeriodo}
              onChange={(evento) => setNuevoPeriodo(evento.target.value)}
              inputMode="numeric"
              maxLength={6}
              mono
              required
              error={errorPeriodo}
              ayuda={
                esPeriodoValido(nuevoPeriodo.trim())
                  ? formatearPeriodo(nuevoPeriodo.trim())
                  : 'Por ejemplo 202606.'
              }
            />
            <CampoAccion>
              <Button type="submit" variante="primario" cargando={crear.isPending}>
                Crear periodo
              </Button>
            </CampoAccion>
          </form>
        </Panel>

        <Panel
          titulo="Periodos registrados"
          descripcion="Sincronizar descarga la propuesta del SIRE y guarda los comprobantes del periodo."
        >
          {periodos.isPending ? <Skeleton lineas={4} etiqueta="Cargando periodos" /> : null}

          {periodos.isError ? (
            <ErrorState
              titulo="No se pudieron cargar los periodos"
              texto={
                periodos.error instanceof ApiError
                  ? periodos.error.message
                  : 'Error inesperado.'
              }
              accion={
                <Button pequeno onClick={() => void periodos.refetch()}>
                  Reintentar
                </Button>
              }
            />
          ) : null}

          {periodos.data ? (
            <DataTable
              leyenda="Periodos fiscales registrados para esta empresa"
              leyendaOculta
              columnas={columnas}
              filas={periodos.data}
              claveDeFila={(fila) => fila.periodo}
              vacio={
                <EmptyState
                  titulo="Todavía no hay periodos"
                  texto="Crea el primero con el formulario de arriba para empezar a sincronizar comprobantes."
                />
              }
            />
          ) : null}
        </Panel>
      </div>

      <Dialog
        abierto={aEliminar !== null}
        titulo={`¿Eliminar el periodo ${aEliminar ? formatearPeriodo(aEliminar.periodo) : ''}?`}
        texto="Se borrarán también todos los comprobantes de ese periodo. La acción no se puede deshacer."
        onCerrar={() => setAEliminar(null)}
        acciones={
          <>
            <Button variante="fantasma" onClick={() => setAEliminar(null)}>
              Cancelar
            </Button>
            <Button
              variante="peligro"
              cargando={borrar.isPending}
              onClick={() => {
                if (aEliminar) borrar.mutate(aEliminar.periodo);
              }}
            >
              Eliminar periodo
            </Button>
          </>
        }
      />
    </>
  );
}
