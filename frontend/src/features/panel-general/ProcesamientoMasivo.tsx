import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import { useState } from 'react';

import { crearSolicitud } from '@/api/solicitudes';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { SolicitudCreate } from '@/types/api';

import estilos from './ProcesamientoMasivo.module.css';
import { mesActual, periodosEntre } from './solicitudes';

const MAX_MESES = 36;

interface Props {
  /** RUC marcados en la tabla de empresas. */
  seleccionados: readonly string[];
  /** Si están marcadas todas: se pide «todas» y no una lista. */
  todas: boolean;
  onEnviada: () => void;
}

type Alcance = 'todos' | 'rango';

/**
 * Lanza una solicitud de procesamiento masivo para las empresas marcadas: por
 * cada empresa y periodo, descarga SIRE, comprobantes y clasificación con IA.
 * Todo corre en el servidor; al terminar llega un correo con el ZIP.
 */
export function ProcesamientoMasivo({ seleccionados, todas, onEnviada }: Props) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const [alcance, setAlcance] = useState<Alcance>('rango');
  const [desde, setDesde] = useState(mesActual());
  const [hasta, setHasta] = useState(mesActual());
  const [clasificar, setClasificar] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const enviar = useMutation({
    mutationFn: (datos: SolicitudCreate) => crearSolicitud(datos),
    onSuccess: async (solicitud) => {
      mostrar({
        tono: 'exito',
        titulo: 'Procesamiento en cola',
        detalle: `${solicitud.progreso.total} empresas × periodos. Puedes cerrar la página: te avisaremos por correo al terminar.`,
      });
      onEnviada();
      await Promise.all([
        cliente.invalidateQueries({ queryKey: ['solicitudes'] }),
        cliente.invalidateQueries({ queryKey: ['resumen-empresas'] }),
        cliente.invalidateQueries({ queryKey: ['jobs'] }),
      ]);
    },
    onError: (fallo) => {
      setError(
        fallo instanceof ApiError ? fallo.message : 'No se pudo lanzar el procesamiento.',
      );
    },
  });

  const periodos = alcance === 'rango' ? periodosEntre(desde, hasta, MAX_MESES + 1) : [];

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setError(null);
    if (!seleccionados.length) {
      setError('Marca al menos una empresa en «Empresas».');
      return;
    }
    if (alcance === 'rango') {
      if (!periodos.length) {
        setError('El mes «desde» tiene que ser anterior o igual al mes «hasta».');
        return;
      }
      if (periodos.length > MAX_MESES) {
        setError(`Como máximo ${MAX_MESES} meses por solicitud.`);
        return;
      }
      if (hasta > mesActual()) {
        setError('El mes «hasta» todavía no ha empezado.');
        return;
      }
    }
    enviar.mutate({
      empresas: todas ? 'todas' : [...seleccionados],
      periodos: alcance === 'todos' ? 'todos' : periodos,
      clasificar,
    });
  }

  const cuantas = seleccionados.length;

  return (
    <Panel
      titulo="Procesamiento masivo"
      descripcion="Descarga SIRE, comprobantes y clasificación con IA de las empresas marcadas, en segundo plano. Al terminar se arma un ZIP con los Excel y los comprobantes y se envía por correo."
    >
      <form className={layout.pila} onSubmit={alEnviar} noValidate>
        <p aria-live="polite">
          {cuantas
            ? `${cuantas} ${cuantas === 1 ? 'empresa seleccionada' : 'empresas seleccionadas'}${todas ? ' (todas)' : ''}.`
            : 'Marca en «Empresas» las que quieres procesar.'}
        </p>

        <fieldset className={estilos.periodos}>
          <legend className={estilos.leyenda}>Periodos</legend>
          <label className={estilos.opcion}>
            <input
              type="radio"
              name="alcance"
              value="rango"
              checked={alcance === 'rango'}
              onChange={() => setAlcance('rango')}
            />
            Un mes o un rango de meses
          </label>
          {alcance === 'rango' ? (
            <div className={estilos.rango}>
              <TextField
                etiqueta="Desde"
                type="month"
                name="desde"
                value={desde}
                max={mesActual()}
                onChange={(evento) => setDesde(evento.target.value)}
              />
              <TextField
                etiqueta="Hasta"
                type="month"
                name="hasta"
                value={hasta}
                max={mesActual()}
                onChange={(evento) => setHasta(evento.target.value)}
              />
            </div>
          ) : null}
          <label className={estilos.opcion}>
            <input
              type="radio"
              name="alcance"
              value="todos"
              checked={alcance === 'todos'}
              onChange={() => setAlcance('todos')}
            />
            Todos los periodos registrados de cada empresa
          </label>
        </fieldset>

        <Checkbox
          etiqueta="Clasificar con IA los comprobantes que no tengan código"
          checked={clasificar}
          onChange={(evento) => setClasificar(evento.target.checked)}
        />

        {error ? (
          <p className={estilos.error} role="alert">
            {error}
          </p>
        ) : null}

        <div className={layout.filaFin}>
          <Button
            type="submit"
            variante="primario"
            cargando={enviar.isPending}
            disabled={!cuantas}
          >
            Procesar
          </Button>
        </div>
      </form>
    </Panel>
  );
}
