import type { ReactNode } from 'react';

import estilos from './Feedback.module.css';

interface PropsEstado {
  titulo: string;
  texto?: string;
  accion?: ReactNode;
}

export function EmptyState({ titulo, texto, accion }: PropsEstado) {
  return (
    <div className={estilos.estado}>
      <p className={estilos.tituloEstado}>{titulo}</p>
      {texto ? <p className={estilos.textoEstado}>{texto}</p> : null}
      {accion}
    </div>
  );
}

/**
 * Error de carga. Lleva `role="alert"` para que un lector de pantalla lo anuncie
 * en cuanto aparece.
 */
export function ErrorState({ titulo, texto, accion }: PropsEstado) {
  return (
    <div className={`${estilos.estado} ${estilos.estadoError ?? ''}`} role="alert">
      <p className={estilos.tituloEstado}>{titulo}</p>
      {texto ? <p className={estilos.textoEstado}>{texto}</p> : null}
      {accion}
    </div>
  );
}

interface PropsEsqueleto {
  /** Número de líneas de marcador de posición. */
  lineas?: number;
  etiqueta?: string;
}

export function Skeleton({ lineas = 3, etiqueta = 'Cargando datos' }: PropsEsqueleto) {
  return (
    <div className={estilos.grupoEsqueletos} role="status" aria-live="polite">
      <span className="visually-hidden">{etiqueta}</span>
      {Array.from({ length: lineas }, (_, indice) => (
        <span
          key={indice}
          className={estilos.esqueleto}
          style={{ inlineSize: `${100 - indice * 12}%` }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}

interface PropsMetrica {
  etiqueta: string;
  valor: string;
  nota?: string;
}

/** Tarjeta de métrica de la fila superior del dashboard. */
export function MetricTile({ etiqueta, valor, nota }: PropsMetrica) {
  return (
    <div className={estilos.metrica}>
      <p className={estilos.etiquetaMetrica}>{etiqueta}</p>
      <p className={estilos.valorMetrica}>{valor}</p>
      {nota ? <p className={estilos.notaMetrica}>{nota}</p> : null}
    </div>
  );
}
