import { useId } from 'react';
import type {
  InputHTMLAttributes,
  Ref,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';

import estilos from './Field.module.css';

interface Comunes {
  etiqueta: string;
  ayuda?: string;
  /** Mensaje de validación. Su presencia marca el control como inválido. */
  error?: string | null;
  mono?: boolean;
}

/** Envuelve etiqueta, control, ayuda y error, y los enlaza por id. */
function Envoltura({
  etiqueta,
  ayuda,
  error,
  idControl,
  idAyuda,
  idError,
  requerido,
  children,
}: Comunes & {
  idControl: string;
  idAyuda: string;
  idError: string;
  requerido?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={estilos.campo}>
      <label className={estilos.etiqueta} htmlFor={idControl}>
        {etiqueta}
        {requerido ? (
          <span className={estilos.requerido} aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children}
      {ayuda ? (
        <p className={estilos.ayuda} id={idAyuda}>
          {ayuda}
        </p>
      ) : null}
      {error ? (
        <p className={estilos.error} id={idError} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(ayuda: string | undefined, error: string | null | undefined, idAyuda: string, idError: string) {
  const ids = [ayuda ? idAyuda : null, error ? idError : null].filter(Boolean);
  return ids.length > 0 ? ids.join(' ') : undefined;
}

type PropsInput = Comunes &
  Omit<InputHTMLAttributes<HTMLInputElement>, 'className' | 'id' | 'aria-invalid'>;

/**
 * Campo de texto. La etiqueta es un `<label>` real enlazado por `htmlFor`; el
 * placeholder nunca hace de etiqueta.
 */
export function TextField({ etiqueta, ayuda, error, mono, required, ...resto }: PropsInput) {
  const base = useId();
  const idControl = `${base}-control`;
  const idAyuda = `${base}-ayuda`;
  const idError = `${base}-error`;

  return (
    <Envoltura
      etiqueta={etiqueta}
      ayuda={ayuda}
      error={error}
      idControl={idControl}
      idAyuda={idAyuda}
      idError={idError}
      requerido={required}
    >
      <input
        {...resto}
        id={idControl}
        required={required}
        className={`${estilos.control} ${mono ? (estilos.mono ?? '') : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ayuda, error, idAyuda, idError)}
      />
    </Envoltura>
  );
}

type PropsTextArea = Comunes &
  Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className' | 'id' | 'aria-invalid'>;

/**
 * Área de texto multilínea. Útil para textos largos que no deben truncarse
 * en un `<input>` de una sola línea (p. ej. descripciones libres).
 */
export function TextAreaField({
  etiqueta,
  ayuda,
  error,
  mono,
  required,
  rows = 4,
  ...resto
}: PropsTextArea) {
  const base = useId();
  const idControl = `${base}-control`;
  const idAyuda = `${base}-ayuda`;
  const idError = `${base}-error`;

  return (
    <Envoltura
      etiqueta={etiqueta}
      ayuda={ayuda}
      error={error}
      idControl={idControl}
      idAyuda={idAyuda}
      idError={idError}
      requerido={required}
    >
      <textarea
        {...resto}
        id={idControl}
        rows={rows}
        required={required}
        className={`${estilos.control} ${estilos.controlArea} ${mono ? (estilos.mono ?? '') : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ayuda, error, idAyuda, idError)}
      />
    </Envoltura>
  );
}

/**
 * Envuelve un control sin etiqueta propia (p. ej. un botón) para que se
 * alinee con los campos vecinos dentro de una `rejillaFormulario`.
 */
export function CampoAccion({ children }: { children: ReactNode }) {
  return (
    <div className={estilos.campo}>
      <span className={estilos.etiqueta} aria-hidden="true">
        &nbsp;
      </span>
      {children}
    </div>
  );
}

export interface Opcion {
  valor: string;
  texto: string;
  /** Opción visible pero no elegible, para explicar por qué no está disponible. */
  deshabilitada?: boolean;
}

type PropsSelect = Comunes &
  Omit<SelectHTMLAttributes<HTMLSelectElement>, 'className' | 'id' | 'children'> & {
    opciones: readonly Opcion[];
  };

export function SelectField({
  etiqueta,
  ayuda,
  error,
  mono,
  opciones,
  required,
  ...resto
}: PropsSelect) {
  const base = useId();
  const idControl = `${base}-control`;
  const idAyuda = `${base}-ayuda`;
  const idError = `${base}-error`;

  return (
    <Envoltura
      etiqueta={etiqueta}
      ayuda={ayuda}
      error={error}
      idControl={idControl}
      idAyuda={idAyuda}
      idError={idError}
      requerido={required}
    >
      <select
        {...resto}
        id={idControl}
        required={required}
        className={`${estilos.control} ${mono ? (estilos.mono ?? '') : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ayuda, error, idAyuda, idError)}
      >
        {opciones.map((opcion) => (
          <option
            key={opcion.valor}
            value={opcion.valor}
            disabled={opcion.deshabilitada}
            className={opcion.deshabilitada ? estilos.opcionInvalida : undefined}
          >
            {opcion.texto}
          </option>
        ))}
      </select>
    </Envoltura>
  );
}

type PropsArchivo = Comunes &
  Omit<InputHTMLAttributes<HTMLInputElement>, 'className' | 'id' | 'type'> & {
    /** React 19 permite `ref` como prop normal; sirve para limpiar el input tras subir. */
    ref?: Ref<HTMLInputElement>;
  };

export function FileField({ etiqueta, ayuda, error, ref, ...resto }: PropsArchivo) {
  const base = useId();
  const idControl = `${base}-control`;
  const idAyuda = `${base}-ayuda`;
  const idError = `${base}-error`;

  return (
    <Envoltura
      etiqueta={etiqueta}
      ayuda={ayuda}
      error={error}
      idControl={idControl}
      idAyuda={idAyuda}
      idError={idError}
    >
      <input
        {...resto}
        ref={ref}
        type="file"
        id={idControl}
        className={estilos.control}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(ayuda, error, idAyuda, idError)}
      />
    </Envoltura>
  );
}
