import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

import {
  eliminarReferencia,
  listarReferencias,
  obtenerTemasBase,
  subirReferencia,
} from '@/api/referencias';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { FileField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';

export function ReferenciasPage() {
  useDocumentTitle('Referencias');

  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const entradaArchivo = useRef<HTMLInputElement>(null);
  const [errorArchivo, setErrorArchivo] = useState<string | null>(null);
  const [aEliminar, setAEliminar] = useState<string | null>(null);

  const referencias = useQuery({
    queryKey: ['referencias', ruc],
    queryFn: () => listarReferencias(ruc),
  });

  const temasBase = useQuery({
    queryKey: ['temas-base', ruc],
    queryFn: () => obtenerTemasBase(ruc),
    staleTime: 10 * 60_000,
  });

  const subir = useMutation({
    mutationFn: (archivo: File) => subirReferencia(ruc, archivo),
    onSuccess: async (respuesta) => {
      // Un PDF sin texto extraíble devuelve `advertencia`, no un error.
      mostrar({
        tono: respuesta.estado === 'advertencia' ? 'neutro' : 'exito',
        titulo: respuesta.mensaje ?? 'Archivo procesado',
        detalle: respuesta.datos ? `${respuesta.datos.chunks} fragmentos indexados.` : undefined,
      });
      if (entradaArchivo.current) entradaArchivo.current.value = '';
      await cliente.invalidateQueries({ queryKey: ['referencias', ruc] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo indexar el PDF',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const borrar = useMutation({
    mutationFn: (nombre: string) => eliminarReferencia(ruc, nombre),
    onSuccess: async (_respuesta, nombre) => {
      mostrar({ tono: 'exito', titulo: `Se eliminó «${nombre}»` });
      setAEliminar(null);
      await cliente.invalidateQueries({ queryKey: ['referencias', ruc] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo eliminar la referencia',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  function alElegir(evento: ChangeEvent<HTMLInputElement>) {
    const archivo = evento.target.files?.[0];
    if (!archivo) return;

    if (!archivo.name.toLowerCase().endsWith('.pdf')) {
      setErrorArchivo('Solo se permiten archivos PDF.');
      return;
    }
    setErrorArchivo(null);
    subir.mutate(archivo);
  }

  const columnas: readonly Columna<string>[] = [
    {
      clave: 'nombre',
      cabecera: 'Documento',
      cabeceraDeFila: true,
      render: (nombre) => nombre,
    },
    {
      clave: 'acciones',
      cabecera: 'Acciones',
      render: (nombre) => (
        <Button pequeno variante="fantasma" onClick={() => setAEliminar(nombre)}>
          Eliminar
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        titulo="Referencias de la empresa"
        descripcion="PDFs que se trocean por página, se convierten en embeddings y se usan como contexto cuando la IA clasifica los comprobantes de esta empresa."
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Subir un documento"
          descripcion="Si el PDF no tiene texto extraíble se recibe igual, pero no aporta contexto: conviene subir PDFs con texto, no escaneos."
        >
          <FileField
            ref={entradaArchivo}
            etiqueta="Documento PDF"
            name="archivo"
            accept="application/pdf"
            onChange={alElegir}
            disabled={subir.isPending}
            error={errorArchivo}
            ayuda={subir.isPending ? 'Indexando el documento…' : 'Un archivo por vez.'}
          />
        </Panel>

        <Panel titulo="Documentos indexados">
          {referencias.isPending ? (
            <Skeleton lineas={3} etiqueta="Cargando referencias" />
          ) : null}

          {referencias.isError ? (
            <ErrorState
              titulo="No se pudieron cargar las referencias"
              texto={
                referencias.error instanceof ApiError
                  ? referencias.error.message
                  : 'Error inesperado.'
              }
              accion={
                <Button pequeno onClick={() => void referencias.refetch()}>
                  Reintentar
                </Button>
              }
            />
          ) : null}

          {referencias.data ? (
            <DataTable
              leyenda="Documentos PDF indexados para esta empresa"
              leyendaOculta
              columnas={columnas}
              filas={referencias.data.archivos}
              claveDeFila={(nombre) => nombre}
              vacio={
                <EmptyState
                  titulo="Sin documentos propios"
                  texto="Sin referencias de la empresa, la IA clasifica usando solo la base de conocimiento general."
                />
              }
            />
          ) : null}
        </Panel>

        <Panel
          titulo="Base de conocimiento general"
          descripcion="Documentos del vector global, comunes a todas las empresas. Se cargan en memoria al arrancar el servidor y no se editan desde aquí."
        >
          {temasBase.isPending ? <Skeleton lineas={2} etiqueta="Cargando temas base" /> : null}
          {temasBase.data ? (
            <ul className={layout.pila}>
              {temasBase.data.temas.map((tema) => (
                <li key={tema} className={layout.textoSecundario}>
                  {tema}
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>
      </div>

      <Dialog
        abierto={aEliminar !== null}
        titulo={`¿Eliminar «${aEliminar ?? ''}»?`}
        texto="Se borrarán todos los fragmentos indexados de ese documento. La IA dejará de usarlo como contexto."
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
                if (aEliminar) borrar.mutate(aEliminar);
              }}
            >
              Eliminar documento
            </Button>
          </>
        }
      />
    </>
  );
}
