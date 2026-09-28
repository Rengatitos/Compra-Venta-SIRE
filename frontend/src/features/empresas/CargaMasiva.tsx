import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ChangeEvent } from 'react';
import { useRef, useState } from 'react';

import { cargarEmpresas, descargarPlantillaCarga } from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { FileField } from '@/components/ui/Field';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';

import { ResultadoCarga } from './ResultadoCarga';

/**
 * Alta de muchas empresas desde un Excel. El archivo se valida al subirlo y
 * cada empresa válida queda registrada al momento; sus datos de SUNAT (token,
 * CIIU, rubro y credenciales del API) se completan en la cola del servidor.
 */
export function CargaMasiva() {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const entrada = useRef<HTMLInputElement>(null);
  const [errorArchivo, setErrorArchivo] = useState<string | null>(null);
  const [cargaId, setCargaId] = useState<string | null>(null);

  const subir = useMutation({
    mutationFn: (archivo: File) => cargarEmpresas(archivo),
    onSuccess: async ({ carga_id }) => {
      setCargaId(carga_id);
      if (entrada.current) entrada.current.value = '';
      // Las válidas ya existen: el selector de empresas debe verlas.
      await cliente.invalidateQueries({ queryKey: ['empresas'] });
    },
    onError: (fallo) => {
      setErrorArchivo(
        fallo instanceof ApiError ? fallo.message : 'No se pudo subir el archivo.',
      );
    },
  });

  function alElegir(evento: ChangeEvent<HTMLInputElement>) {
    const archivo = evento.target.files?.[0];
    if (!archivo) return;
    if (!/\.xlsx$|\.xlsm$/i.test(archivo.name)) {
      setErrorArchivo('Solo se permiten archivos Excel (.xlsx o .xlsm).');
      return;
    }
    setErrorArchivo(null);
    subir.mutate(archivo);
  }

  async function alDescargarPlantilla() {
    try {
      await descargarPlantillaCarga();
    } catch (fallo) {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo descargar la plantilla',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    }
  }

  return (
    <div className={layout.pilaAmplia}>
      <div className={layout.pila}>
        <p className={layout.textoSecundario}>
          Columnas A a D de la primera hoja, en este orden: <strong>Razón social</strong>,{' '}
          <strong>RUC</strong>, <strong>Usuario</strong> y <strong>Contraseña</strong> SOL. La
          fila de cabecera es opcional y cualquier otra columna se ignora. Por cada empresa se
          obtienen solos sus credenciales del API SUNAT, el CIIU y el rubro.
        </p>
        <div className={layout.fila}>
          <Button variante="fantasma" pequeno onClick={() => void alDescargarPlantilla()}>
            Descargar plantilla
          </Button>
        </div>
        <FileField
          ref={entrada}
          etiqueta="Archivo Excel"
          name="archivo"
          accept=".xlsx,.xlsm"
          onChange={alElegir}
          disabled={subir.isPending}
          error={errorArchivo}
          ayuda={subir.isPending ? 'Validando las empresas…' : 'Hasta 200 empresas y 2 MB.'}
        />
      </div>

      {cargaId ? (
        <ResultadoCarga
          cargaId={cargaId}
          onTerminada={() => {
            void cliente.invalidateQueries({ queryKey: ['empresas'] });
          }}
        />
      ) : null}
    </div>
  );
}
