import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import { useEffect, useRef, useState } from 'react';

import { guardarCorreos } from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { EmpresaResponse } from '@/types/api';

import { ANCLA_CORREOS, MAX_CORREOS, esCorreoValido } from './correos';
import estilos from './CorreosEmpresaPanel.module.css';

interface Props {
  ruc: string;
  empresa: EmpresaResponse | undefined;
}

/**
 * Correos a los que se envían los resultados de esta empresa cuando termina una
 * solicitud de procesamiento masivo. Cada correo recibe solo las empresas a
 * las que está asociado, nunca las de otros clientes.
 */
export function CorreosEmpresaPanel({ ruc, empresa }: Props) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const seccion = useRef<HTMLDivElement>(null);
  const guardados = empresa?.correos_notificacion ?? [];
  const [lista, setLista] = useState<string[]>(guardados);
  const [nuevo, setNuevo] = useState('');
  const [error, setError] = useState<string | null>(null);

  // La lista local sigue a la guardada cuando llega o cambia desde fuera.
  const firmaGuardados = guardados.join('|');
  useEffect(() => {
    setLista(firmaGuardados ? firmaGuardados.split('|') : []);
  }, [firmaGuardados]);

  // El panel general enlaza a `/ajustes#correos`.
  useEffect(() => {
    if (window.location.hash === `#${ANCLA_CORREOS}`) {
      seccion.current?.scrollIntoView({ block: 'start' });
    }
  }, []);

  const guardar = useMutation({
    mutationFn: (correos: string[]) => guardarCorreos(ruc, correos),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Correos guardados' });
      await Promise.all([
        cliente.invalidateQueries({ queryKey: ['empresa', ruc] }),
        cliente.invalidateQueries({ queryKey: ['empresas'] }),
        cliente.invalidateQueries({ queryKey: ['resumen-empresas'] }),
      ]);
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudieron guardar los correos',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  function agregar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const correo = nuevo.trim().toLowerCase();
    if (!esCorreoValido(correo)) {
      setError('Escribe un correo válido, por ejemplo contabilidad@empresa.pe.');
      return;
    }
    if (lista.includes(correo)) {
      setError('Ese correo ya está en la lista.');
      return;
    }
    if (lista.length >= MAX_CORREOS) {
      setError(`Como máximo ${MAX_CORREOS} correos por empresa.`);
      return;
    }
    setError(null);
    setLista([...lista, correo]);
    setNuevo('');
  }

  const cambio = lista.join('|') !== firmaGuardados;

  return (
    <div id={ANCLA_CORREOS} ref={seccion}>
      <Panel
        titulo="Correos para envío de resultados"
        descripcion="Al terminar una solicitud de procesamiento masivo que incluya esta empresa, cada correo recibe el ZIP con sus archivos (o un enlace para descargarlo)."
      >
        <div className={layout.pila}>
          {lista.length ? (
            <ul className={estilos.lista} aria-label="Correos de la empresa">
              {lista.map((correo) => (
                <li key={correo} className={estilos.correo}>
                  <span>{correo}</span>
                  <Button
                    pequeno
                    variante="fantasma"
                    aria-label={`Quitar ${correo}`}
                    onClick={() => setLista(lista.filter((c) => c !== correo))}
                  >
                    Quitar
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className={layout.textoSecundario}>Todavía no hay correos para esta empresa.</p>
          )}

          <form className={estilos.agregar} onSubmit={agregar} noValidate>
            <TextField
              etiqueta="Nuevo correo"
              name="correo"
              type="email"
              value={nuevo}
              onChange={(evento) => setNuevo(evento.target.value)}
              error={error}
              autoComplete="off"
            />
            <Button type="submit" variante="secundario">
              Agregar
            </Button>
          </form>

          <div className={layout.filaFin}>
            <Button
              variante="primario"
              disabled={!cambio}
              cargando={guardar.isPending}
              onClick={() => guardar.mutate(lista)}
            >
              Guardar correos
            </Button>
          </div>
        </div>
      </Panel>
    </div>
  );
}
