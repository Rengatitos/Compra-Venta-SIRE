import { useMutation } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import type { CSSProperties } from 'react';
import { Link } from 'react-router';

import { generarCodigoVinculacion } from '@/api/empresas';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import type { CodigoVinculacion } from '@/types/api';

import estilos from './VinculacionBotPanel.module.css';

/** Lo que dura un código en el servidor (`vinculacion_service.VIGENCIA`). */
const VIGENCIA_S = 10 * 60;

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

/**
 * Lo primero de los ajustes: el código con el que una persona conecta Apaclla
 * Bot a esta empresa. El código se muestra en la propia tarjeta —no en un
 * diálogo— para poder dictarlo o copiarlo mientras se mira el chat.
 */
export function VinculacionBotPanel({ ruc }: { ruc: string }) {
  const { mostrar } = useToast();
  const idTitulo = useId();
  const [codigo, setCodigo] = useState<CodigoVinculacion | null>(null);
  const restantes = useCuentaRegresiva(codigo?.expira_en ?? null);
  const vencido = codigo !== null && restantes === 0;
  const vigente = codigo !== null && !vencido;

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
    <section className={estilos.tarjeta} aria-labelledby={idTitulo}>
      <div className={estilos.intro}>
        <div className={estilos.cabecera}>
          <h2 className={estilos.titulo} id={idTitulo}>
            Conectar Apaclla Bot
          </h2>
          {vigente ? (
            <Badge tono="exito" conPunto>
              Código activo
            </Badge>
          ) : null}
        </div>
        <p className={estilos.lead}>
          Con un código de 6 dígitos, cualquier persona conecta su chat de Apaclla Bot a esta
          empresa y empieza a registrar comprobantes desde el celular.
        </p>
        <ol className={estilos.pasos}>
          <li>
            <span className={estilos.numero} aria-hidden="true">
              1
            </span>
            <span>Genera el código aquí.</span>
          </li>
          <li>
            <span className={estilos.numero} aria-hidden="true">
              2
            </span>
            <span>
              En Apaclla Bot, escribe el RUC <strong className={estilos.mono}>{ruc}</strong> y el
              código.
            </span>
          </li>
          <li>
            <span className={estilos.numero} aria-hidden="true">
              3
            </span>
            <span>
              Lo que registre aparece en{' '}
              <Link to="/externos" className={estilos.enlace}>
                Comprobantes externos
              </Link>
              .
            </span>
          </li>
        </ol>
      </div>

      <div className={estilos.zonaCodigo}>
        {codigo ? (
          <>
            <p className={estilos.etiqueta}>Código de vinculación</p>
            <p className={`${estilos.digitos} ${vencido ? (estilos.vencido ?? '') : ''}`}>
              {/* Separado para que el lector de pantalla lo diga dígito a dígito. */}
              <span className="visually-hidden">{`Código ${codigo.codigo.split('').join(' ')}`}</span>
              {codigo.codigo.split('').map((digito, i) => (
                // El índice es la identidad: la posición del dígito.
                <span key={i} className={estilos.digito} aria-hidden="true">
                  {digito}
                </span>
              ))}
            </p>
            <div
              className={estilos.barra}
              aria-hidden="true"
              style={{ '--avance': `${(restantes / VIGENCIA_S) * 100}%` } as CSSProperties}
            />
            <p className={estilos.cuenta} role="timer" aria-live="off">
              {vencido
                ? 'Este código venció. Genera otro.'
                : `Vence en ${formatearCuenta(restantes)}`}
            </p>
            <div className={estilos.acciones}>
              {vencido ? (
                <Button
                  variante="primario"
                  onClick={() => generar.mutate()}
                  cargando={generar.isPending}
                >
                  Generar otro
                </Button>
              ) : (
                <>
                  <Button variante="primario" onClick={() => void copiar()}>
                    Copiar código
                  </Button>
                  <Button
                    variante="fantasma"
                    onClick={() => generar.mutate()}
                    cargando={generar.isPending}
                  >
                    Generar otro
                  </Button>
                </>
              )}
            </div>
          </>
        ) : (
          <>
            <p className={estilos.digitos} aria-hidden="true">
              {Array.from({ length: 6 }, (_, i) => (
                <span key={i} className={`${estilos.digito} ${estilos.vacio ?? ''}`}>
                  ·
                </span>
              ))}
            </p>
            <Button
              variante="primario"
              onClick={() => generar.mutate()}
              cargando={generar.isPending}
            >
              Generar código
            </Button>
          </>
        )}
        <p className={estilos.nota}>
          Vale 10 minutos y un solo uso. Generar otro anula el anterior.
        </p>
      </div>
    </section>
  );
}
