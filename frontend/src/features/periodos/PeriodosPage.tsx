import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router';

import { crearPeriodo, eliminarPeriodo, listarPeriodos } from '@/api/periodos';
import { sincronizarPropuesta } from '@/api/propuesta';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { CampoAccion, SelectField } from '@/components/ui/Field';
import type { Opcion } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import {
  aniosDisponibles,
  componerPeriodo,
  formatearPeriodo,
  MESES,
  partirPeriodo,
  periodoPorDefecto,
} from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { PeriodoResponse } from '@/types/api';
import { esPeriodoValido } from '@/types/domain';

import { presentarEstadoPeriodo } from './estadoPeriodo';

const ANIOS: readonly Opcion[] = aniosDisponibles().map((anio) => ({
  valor: anio,
  texto: anio,
}));

/**
 * El mes más reciente que todavía no existe, caminando hacia atrás desde el
 * periodo por defecto. Sin esto el formulario abre con el mes anterior ya
 * creado y el botón solo sirve para dar un error.
 */
function primerPeriodoLibre(registrados: ReadonlySet<string>): string {
  const partida = periodoPorDefecto();
  let anio = Number(partida.slice(0, 4));
  let mes = Number(partida.slice(4, 6));
  const limite = Number(ANIOS.at(-1)?.valor ?? anio);

  while (anio >= limite) {
    const candidato = componerPeriodo(String(anio), String(mes));
    if (!registrados.has(candidato)) return candidato;
    mes -= 1;
    if (mes === 0) {
      mes = 12;
      anio -= 1;
    }
  }
  return partida;
}

export function PeriodosPage() {
  useDocumentTitle('Periodos');

  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [seleccion, setSeleccion] = useState(() => partirPeriodo(periodoPorDefecto()));
  const [errorPeriodo, setErrorPeriodo] = useState<string | null>(null);
  const [aEliminar, setAEliminar] = useState<PeriodoResponse | null>(null);

  const periodos = useQuery({
    queryKey: ['periodos', ruc],
    queryFn: () => listarPeriodos(ruc),
  });

  const nuevoPeriodo = componerPeriodo(seleccion.anio, seleccion.mes);

  // Los meses que ya existen se ofrecen deshabilitados en lugar de dejar que el
  // envío choque contra el 409 del backend.
  const registrados = useMemo(
    () => new Set((periodos.data ?? []).map((fila) => fila.periodo)),
    [periodos.data],
  );

  // Solo se reposiciona la primera vez que llegan los periodos: a partir de ahí
  // manda lo que haya elegido el usuario.
  const ajustado = useRef(false);
  useEffect(() => {
    if (ajustado.current || !periodos.data) return;
    ajustado.current = true;
    if (registrados.has(nuevoPeriodo)) {
      setSeleccion(partirPeriodo(primerPeriodoLibre(registrados)));
    }
  }, [periodos.data, registrados, nuevoPeriodo]);

  const meses: readonly Opcion[] = MESES.map((nombre, indice) => {
    const mes = String(indice + 1).padStart(2, '0');
    const yaExiste = registrados.has(componerPeriodo(seleccion.anio, mes));
    return {
      valor: mes,
      texto: yaExiste
        ? `${nombre.charAt(0).toUpperCase()}${nombre.slice(1)} · ya registrado`
        : `${nombre.charAt(0).toUpperCase()}${nombre.slice(1)}`,
      deshabilitada: yaExiste,
    };
  });

  // Crear, sincronizar o borrar un periodo cambia también lo que el panel puede
  // ofrecer en su selector, así que se invalida la analítica junto al listado.
  async function invalidarPeriodos() {
    await cliente.invalidateQueries({ queryKey: ['periodos', ruc] });
    await cliente.invalidateQueries({ queryKey: ['analytics-periodos', ruc] });
    await cliente.invalidateQueries({ queryKey: ['dashboard', ruc] });
  }

  const crear = useMutation({
    mutationFn: (periodo: string) => crearPeriodo(ruc, periodo),
    onSuccess: async (creado) => {
      mostrar({
        tono: 'exito',
        titulo: `Periodo ${formatearPeriodo(creado.periodo)} creado`,
        detalle: 'Sincronizando su propuesta de compras…',
      });
      await invalidarPeriodos();
      sincronizar.mutate(creado.periodo);
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
    if (!esPeriodoValido(nuevoPeriodo)) {
      setErrorPeriodo('Elige un mes y un año válidos.');
      return;
    }
    if (registrados.has(nuevoPeriodo)) {
      setErrorPeriodo('Ese periodo ya existe para esta empresa.');
      return;
    }
    setErrorPeriodo(null);
    crear.mutate(nuevoPeriodo);
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
          <ButtonLink
            a={`/periodos/${encodeURIComponent(fila.periodo)}`}
            variante="primario"
            pequeno
          >
            Ver comprobantes
          </ButtonLink>
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
          descripcion="Elige el mes y el año. Los meses que ya tienes registrados aparecen deshabilitados."
        >
          <form className={layout.rejillaFormulario} onSubmit={alCrear} noValidate>
            <SelectField
              etiqueta="Mes"
              name="mes"
              value={seleccion.mes}
              onChange={(evento) =>
                setSeleccion((actual) => ({ ...actual, mes: evento.target.value }))
              }
              opciones={meses}
              required
              error={errorPeriodo}
              ayuda={`Se registrará como ${nuevoPeriodo}.`}
            />
            <SelectField
              etiqueta="Año"
              name="anio"
              value={seleccion.anio}
              onChange={(evento) =>
                setSeleccion((actual) => ({ ...actual, anio: evento.target.value }))
              }
              opciones={ANIOS}
              mono
              required
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
          descripcion="Al crear un periodo se sincroniza automáticamente su propuesta del SIRE."
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
