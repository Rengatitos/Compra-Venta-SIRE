import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { generarCodigoVinculacion } from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { Panel } from '@/components/ui/Panel';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { CodigoVinculacion } from '@/types/api';

import estilos from './VinculacionBotPanel.module.css';

function segundosRestantes(expiraEn: string, ahora = Date.now()): number {
  return Math.max(0, Math.floor((new Date(expiraEn).getTime() - ahora) / 1000));
}

function formatearCuenta(segundos: number): string {
  const minutos = Math.floor(segundos / 60);
  return `${minutos}:${String(segundos % 60).padStart(2, '0')}`;
}

/** Cuenta regresiva hasta `expiraEn`, en segundos. */
function useCuentaRegresiva(expiraEn: string | null): number {
  const [restantes, setRestantes] = useState(() =>
    expiraEn ? segundosRestantes(expiraEn) : 0,
  );

  useEffect(() => {
    if (!expiraEn) return;
    setRestantes(segundosRestantes(expiraEn));
    const intervalo = window.setInterval(() => setRestantes(segundosRestantes(expiraEn)), 1000);
    return () => window.clearInterval(intervalo);
  }, [expiraEn]);

  return restantes;
}

export function VinculacionBotPanel({ ruc }: { ruc: string }) {
  const { mostrar } = useToast();
  const [codigo, setCodigo] = useState<CodigoVinculacion | null>(null);
  const restantes = useCuentaRegresiva(codigo?.expira_en ?? null);
  const vencido = codigo !== null && restantes === 0;

  const generar = useMutation({
    mutationFn: () => generarCodigoVinculacion(ruc),
    onSuccess: setCodigo,
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo generar el código',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  async function copiar() {
    if (!codigo) return;
    try {
      await navigator.clipboard.writeText(codigo.codigo);
      mostrar({ tono: 'exito', titulo: 'Código copiado' });
    } catch {
      mostrar({ tono: 'error', titulo: 'No se pudo copiar; escríbelo a mano' });
    }
  }

  return (
    <>
      <Panel
        titulo="Vinculación con Apaclla Bot"
        descripcion="Genera un código para que una persona conecte Apaclla Bot con esta empresa. Lo que registre desde el chat aparece en Comprobantes externos. El código vence a los 10 minutos, sirve una sola vez y generar otro anula el anterior."
      >
        <div className={layout.filaFin}>
          <Button onClick={() => generar.mutate()} cargando={generar.isPending}>
            Generar código
          </Button>
        </div>
      </Panel>

      <Dialog
        abierto={codigo !== null}
        titulo="Código de vinculación"
        texto={`En Apaclla Bot, escribe el RUC ${ruc} y este código.`}
        onCerrar={() => setCodigo(null)}
        acciones={
          <>
            {vencido ? (
              <Button onClick={() => generar.mutate()} cargando={generar.isPending}>
                Generar otro
              </Button>
            ) : (
              <Button onClick={() => void copiar()}>Copiar código</Button>
            )}
            <Button variante="primario" onClick={() => setCodigo(null)}>
              Listo
            </Button>
          </>
        }
      >
        {codigo ? (
          <div className={estilos.contenido}>
            <p
              className={`${estilos.codigo} ${vencido ? (estilos.vencido ?? '') : ''}`}
              aria-label={`Código ${codigo.codigo.split('').join(' ')}`}
            >
              {codigo.codigo}
            </p>
            <p className={estilos.cuenta} role="timer" aria-live="off">
              {vencido
                ? 'Este código venció. Genera otro.'
                : `Vence en ${formatearCuenta(restantes)}`}
            </p>
          </div>
        ) : null}
      </Dialog>
    </>
  );
}
