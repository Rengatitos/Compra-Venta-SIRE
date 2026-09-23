import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import { useLocation } from 'react-router';

import { buscarCiiu, guardarActividades, obtenerCiiuEmpresa } from '@/api/empresas';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useToast } from '@/hooks/useToast';
import { formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ActividadEconomica, EmpresaResponse } from '@/types/api';

import { ANCLA_ACTIVIDADES, principalEfectiva } from './actividades';
import estilos from './ActividadesEmpresaPanel.module.css';

function detalle(fallo: unknown): string {
  return fallo instanceof ApiError ? fallo.message : 'Error inesperado.';
}

/**
 * Actividades económicas (CIIU) con las que el clasificador interpreta cada
 * comprobante. Salen de la ficha RUC de SUNAT, pero la ficha no siempre dice a
 * qué se dedica de verdad el negocio: un restaurante puede figurar como venta
 * de electrodomésticos. Por eso aquí se agregan actividades del catálogo CIIU,
 * se quitan las que no sirven y se elige cuál manda al clasificar.
 */
export function ActividadesEmpresaPanel({
  ruc,
  empresa,
}: {
  ruc: string;
  empresa: EmpresaResponse | undefined;
}) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const idGrupo = useId();

  const [lista, setLista] = useState<ActividadEconomica[]>([]);
  const [principal, setPrincipal] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState('');

  // El borrador se rehace cada vez que llega la empresa del servidor: tras
  // guardar o tras consultar SUNAT, lo que se ve es lo guardado.
  useEffect(() => {
    setLista(empresa?.actividades_economicas ?? []);
    setPrincipal(principalEfectiva(empresa));
  }, [empresa]);

  // Desde el «editar» del Dashboard se llega con `#actividades`. El router no
  // salta a anclas por su cuenta, y el panel no existe hasta que carga la
  // empresa: se baja a él en cuanto está.
  const { hash } = useLocation();
  const cargada = empresa !== undefined;
  useEffect(() => {
    if (cargada && hash === `#${ANCLA_ACTIVIDADES}`) {
      document.getElementById(ANCLA_ACTIVIDADES)?.scrollIntoView({ block: 'start' });
    }
  }, [cargada, hash]);

  const guardadas = empresa?.actividades_economicas ?? [];
  const cambiado =
    JSON.stringify(lista.map((a) => a.ciiu)) !== JSON.stringify(guardadas.map((a) => a.ciiu)) ||
    principal !== principalEfectiva(empresa);

  const refrescar = () => cliente.invalidateQueries({ queryKey: ['empresa', ruc] });

  const guardar = useMutation({
    mutationFn: () => guardarActividades(ruc, lista, principal),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Actividades guardadas' });
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudieron guardar', detalle: detalle(fallo) }),
  });

  const deSunat = useMutation({
    mutationFn: () => obtenerCiiuEmpresa(ruc),
    onSuccess: async () => {
      mostrar({
        tono: 'exito',
        titulo: 'Actividades de SUNAT actualizadas',
        detalle: 'Las que agregaste a mano se conservan.',
      });
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo consultar la ficha RUC',
        detalle: detalle(fallo),
      }),
  });

  const consulta = busqueda.trim();
  const resultados = useQuery({
    queryKey: ['ciiu', consulta],
    queryFn: () => buscarCiiu(consulta),
    enabled: consulta.length >= 2,
    staleTime: Infinity,
  });

  function agregar(ciiu: string, descripcion: string) {
    if (lista.some((a) => a.ciiu === ciiu)) return;
    setLista([...lista, { tipo: null, ciiu, descripcion, origen: 'manual' }]);
    setBusqueda('');
  }

  function quitar(ciiu: string) {
    setLista(lista.filter((a) => a.ciiu !== ciiu));
    if (principal === ciiu) setPrincipal(null);
  }

  const ficha = empresa?.ficha_ruc;

  return (
    <div id={ANCLA_ACTIVIDADES} className={estilos.ancla}>
      <Panel
        titulo="Actividades económicas (CIIU)"
        descripcion="Con ellas la IA interpreta cada compra y venta. Elige la que describe tu negocio de verdad: manda al clasificar, aunque SUNAT diga otra. Las demás quedan como contexto."
        acciones={
          <Button onClick={() => deSunat.mutate()} cargando={deSunat.isPending}>
            Obtener CIIU desde SUNAT
          </Button>
        }
      >
        {lista.length > 0 ? (
          <fieldset className={estilos.grupo} aria-describedby={idGrupo}>
            <legend className={estilos.leyenda}>Principal para clasificar</legend>
            <ul className={estilos.lista}>
              {lista.map((actividad) => (
                <li key={actividad.ciiu} className={estilos.fila}>
                  <label className={estilos.opcion}>
                    <input
                      type="radio"
                      name="ciiu-principal"
                      checked={principal === actividad.ciiu}
                      onChange={() => setPrincipal(actividad.ciiu)}
                    />
                    <span>
                      <strong>{actividad.ciiu}</strong> —{' '}
                      {actividad.descripcion || 'Sin descripción'}
                    </span>
                  </label>
                  <span className={layout.fila}>
                    {actividad.origen === 'manual' ? (
                      <Badge tono="info">Agregada</Badge>
                    ) : (
                      <Badge tono="neutro">
                        SUNAT{actividad.tipo === 'PRINCIPAL' ? ' · principal' : ''}
                      </Badge>
                    )}
                    <Button
                      pequeno
                      variante="fantasma"
                      onClick={() => quitar(actividad.ciiu)}
                      aria-label={`Quitar la actividad ${actividad.ciiu}`}
                    >
                      Quitar
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
            <p id={idGrupo} className={layout.textoSecundario}>
              Quitar una actividad solo la saca de la clasificación; si es de SUNAT, vuelve la
              próxima vez que consultes la ficha.
            </p>
          </fieldset>
        ) : (
          <p className={layout.textoSecundario}>
            Aún no hay actividades. Consúltalas en SUNAT o agrégalas desde el catálogo.
          </p>
        )}

        <div className={estilos.buscador}>
          <TextField
            etiqueta="Agregar actividad del catálogo CIIU"
            value={busqueda}
            onChange={(evento) => setBusqueda(evento.target.value)}
            placeholder="Código o palabras, p. ej. 5610 o restaurantes"
            autoComplete="off"
          />
          {consulta.length >= 2 && resultados.data ? (
            resultados.data.length === 0 ? (
              <p className={layout.textoSecundario}>Ninguna actividad coincide.</p>
            ) : (
              <ul className={estilos.lista}>
                {resultados.data.map((clase) => (
                  <li key={clase.ciiu} className={estilos.fila}>
                    <span>
                      <strong>{clase.ciiu}</strong> — {clase.descripcion}
                    </span>
                    <Button
                      pequeno
                      onClick={() => agregar(clase.ciiu, clase.descripcion)}
                      disabled={lista.some((a) => a.ciiu === clase.ciiu)}
                    >
                      {lista.some((a) => a.ciiu === clase.ciiu) ? 'Ya está' : 'Agregar'}
                    </Button>
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>

        <div className={layout.filaFin}>
          <Button
            variante="primario"
            onClick={() => guardar.mutate()}
            cargando={guardar.isPending}
            disabled={!cambiado}
          >
            Guardar actividades
          </Button>
        </div>

        {ficha ? (
          <p className={layout.textoSecundario}>
            Ficha RUC:{' '}
            {[ficha.razon_social, ficha.estado, ficha.condicion].filter(Boolean).join(' · ')} ·
            consultada {formatearFechaHora(ficha.consultado_en)}
          </p>
        ) : null}
      </Panel>
    </div>
  );
}
