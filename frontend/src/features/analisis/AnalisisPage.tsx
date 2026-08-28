import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { Link, useParams } from 'react-router';

import { ejecutarAnalisis } from '@/api/analisis';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { ErrorState, MetricTile } from '@/components/ui/Feedback';
import { FileField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { NoEncontradaPage } from '@/features/shared/NoEncontradaPage';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearEntero, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ResultadoAnalisis } from '@/types/api';
import { esPeriodoValido } from '@/types/domain';

export function AnalisisPage() {
  const { periodo = '' } = useParams();
  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [archivos, setArchivos] = useState<File[]>([]);
  const [errorArchivos, setErrorArchivos] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoAnalisis | null>(null);

  useDocumentTitle(`Análisis IA ${formatearPeriodo(periodo)}`);

  const analizar = useMutation({
    mutationFn: () => ejecutarAnalisis(ruc, periodo, archivos),
    onSuccess: async (respuesta) => {
      setResultado(respuesta.datos);
      mostrar({
        tono: 'exito',
        titulo: respuesta.mensaje ?? 'Análisis completado',
        detalle: respuesta.datos
          ? `${respuesta.datos.procesadas} de ${respuesta.datos.total_encontradas} comprobantes procesados.`
          : undefined,
      });
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'El análisis no se completó',
        detalle:
          fallo instanceof ApiError && fallo.esLimiteDeTasa
            ? 'El análisis admite 5 ejecuciones por minuto. Espera un momento.'
            : fallo instanceof ApiError
              ? fallo.message
              : 'Error inesperado.',
      });
    },
  });

  if (!esPeriodoValido(periodo)) return <NoEncontradaPage />;

  function alElegirArchivos(evento: ChangeEvent<HTMLInputElement>) {
    const seleccionados = Array.from(evento.target.files ?? []);
    const noPdf = seleccionados.filter(
      (archivo) => !archivo.name.toLowerCase().endsWith('.pdf'),
    );

    if (noPdf.length > 0) {
      setErrorArchivos('Solo se aceptan archivos PDF. El backend ignora el resto.');
    } else {
      setErrorArchivos(null);
    }

    setArchivos(seleccionados.filter((archivo) => archivo.name.toLowerCase().endsWith('.pdf')));
  }

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setResultado(null);
    analizar.mutate();
  }

  return (
    <>
      <PageHeader
        titulo="Análisis contable con IA"
        descripcion="Clasifica con Gemini todos los comprobantes del periodo que estén pendientes de análisis o que fallaron en un intento anterior."
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Contexto adicional"
          descripcion="Los PDFs que adjuntes aquí se indexan solo para esta corrida y se descartan al terminar. Si no adjuntas nada se usa el contexto que la empresa ya tenga indexado en Referencias."
        >
          <form className={layout.pila} onSubmit={alEnviar}>
            <FileField
              etiqueta="PDFs de contexto"
              name="archivos"
              accept="application/pdf"
              multiple
              onChange={alElegirArchivos}
              error={errorArchivos}
              ayuda={
                archivos.length > 0
                  ? `${archivos.length} PDF(s) listos para esta corrida.`
                  : 'Sin adjuntos se usa el contexto permanente de la empresa.'
              }
            />

            <p className={layout.textoSecundario}>
              El rubro que orienta la clasificación no se elige aquí: se deduce del CIIU dentro
              del token de SUNAT guardado en la empresa.
            </p>

            <div className={layout.filaFin}>
              <Button type="submit" variante="primario" cargando={analizar.isPending}>
                {analizar.isPending ? 'Analizando…' : 'Ejecutar análisis'}
              </Button>
            </div>

            {analizar.isPending ? (
              <p className={layout.textoSecundario} role="status" aria-live="polite">
                El análisis es sincrónico y puede tardar varios minutos según el número de
                comprobantes. No cierres esta pestaña.
              </p>
            ) : null}
          </form>
        </Panel>

        {resultado ? (
          <Panel
            titulo="Resultado de la corrida"
            descripcion="Un fallo en un comprobante concreto no detiene la corrida: queda marcado como error de análisis y se cuenta aparte."
          >
            <div className={layout.rejillaMetricas}>
              <MetricTile
                etiqueta="Encontrados"
                valor={formatearEntero(resultado.total_encontradas)}
                nota="Comprobantes pendientes de análisis"
              />
              <MetricTile
                etiqueta="Procesados"
                valor={formatearEntero(resultado.procesadas)}
                nota="Clasificados correctamente"
              />
              <MetricTile
                etiqueta="Errores"
                valor={formatearEntero(resultado.errores)}
                nota="Se pueden reintentar"
              />
              <MetricTile
                etiqueta="Sin datos"
                valor={formatearEntero(resultado.sin_datos)}
                nota="La IA no encontró información suficiente"
              />
            </div>
            <p className={layout.textoSecundario}>
              <Link to={`/periodos/${encodeURIComponent(periodo)}`}>
                Ver los comprobantes del periodo
              </Link>
            </p>
          </Panel>
        ) : null}

        {analizar.isError ? (
          <ErrorState
            titulo="El análisis no se completó"
            texto={
              analizar.error instanceof ApiError
                ? analizar.error.message
                : 'Error inesperado al orquestar el análisis.'
            }
            accion={
              <Button pequeno onClick={() => analizar.mutate()}>
                Reintentar
              </Button>
            }
          />
        ) : null}
      </div>
    </>
  );
}
