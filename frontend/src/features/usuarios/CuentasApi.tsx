import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import {
  crearCuentaApi,
  eliminarCuentaApi,
  listarCuentasApi,
  regenerarCuentaApi,
} from '@/api/cuentasApi';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { SelectField, TextField } from '@/components/ui/Field';
import { useToast } from '@/hooks/useToast';
import { formatearFecha, formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { CuentaApiConClave, RolUsuario } from '@/types/api';

import estilos from './GestionAccesos.module.css';

const ROLES = [
  { valor: 'usuario', texto: 'Usuario (lee datos y lanza procesos)' },
  { valor: 'admin', texto: 'Administrador (además gestiona accesos)' },
] as const;

const VIGENCIAS = [
  { valor: '30', texto: '30 días' },
  { valor: '90', texto: '90 días' },
  { valor: '180', texto: '180 días' },
  { valor: '365', texto: '1 año' },
] as const;

const URL_TOKEN = `${window.location.origin}/api/v1/auth/token`;

function detalle(fallo: unknown): string {
  return fallo instanceof ApiError ? fallo.message : 'Error inesperado.';
}

function curlDe(email: string, password: string): string {
  return [
    `curl -s -X POST "${URL_TOKEN}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"email": "${email}", "password": "${password}"}'`,
  ].join('\n');
}

/**
 * La contraseña recién generada. Sire no la guarda: si se cierra sin copiarla,
 * hay que regenerarla.
 */
function ClaveNueva({ nueva, alCerrar }: { nueva: CuentaApiConClave; alCerrar: () => void }) {
  const { mostrar } = useToast();
  const curl = curlDe(nueva.cuenta.email, nueva.password);

  async function copiar(texto: string, que: string) {
    try {
      await navigator.clipboard.writeText(texto);
      mostrar({ tono: 'exito', titulo: `${que} copiado` });
    } catch {
      mostrar({ tono: 'error', titulo: 'No se pudo copiar', detalle: 'Selecciónalo y cópialo a mano.' });
    }
  }

  return (
    <div className={estilos.claveNueva} role="status">
      <p className={estilos.titulo}>Contraseña de {nueva.cuenta.email}</p>
      <p className={layout.textoSecundario}>
        Cópiala ahora: no se vuelve a mostrar. Vence el {formatearFecha(nueva.cuenta.expira_en)}.
      </p>
      <code className={estilos.codigo}>{nueva.password}</code>
      <pre className={estilos.codigo}>{curl}</pre>
      <span className={layout.fila}>
        <Button pequeno variante="primario" onClick={() => void copiar(nueva.password, 'Contraseña')}>
          Copiar contraseña
        </Button>
        <Button pequeno onClick={() => void copiar(curl, 'curl')}>
          Copiar curl
        </Button>
        <Button pequeno variante="fantasma" onClick={alCerrar}>
          Ya la guardé
        </Button>
      </span>
    </div>
  );
}

/**
 * Cuentas de API: correo y contraseña para que un programa (ELT, scripts)
 * obtenga su token con `POST /api/v1/auth/token`, sin Google ni el panel.
 */
export function CuentasApi() {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const [correo, setCorreo] = useState('');
  const [rol, setRol] = useState<RolUsuario>('usuario');
  const [vigencia, setVigencia] = useState('90');
  const [nueva, setNueva] = useState<CuentaApiConClave | null>(null);

  const cuentas = useQuery({ queryKey: ['cuentas-api'], queryFn: listarCuentasApi });
  const refrescar = () => cliente.invalidateQueries({ queryKey: ['cuentas-api'] });

  const crear = useMutation({
    mutationFn: () => crearCuentaApi(correo.trim(), rol, Number(vigencia)),
    onSuccess: async (resultado) => {
      setNueva(resultado);
      setCorreo('');
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo crear la cuenta', detalle: detalle(fallo) }),
  });

  const regenerar = useMutation({
    mutationFn: (email: string) => regenerarCuentaApi(email),
    onSuccess: async (resultado) => {
      setNueva(resultado);
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo generar la contraseña', detalle: detalle(fallo) }),
  });

  const eliminar = useMutation({
    mutationFn: (email: string) => eliminarCuentaApi(email),
    onSuccess: async (_vacio, email) => {
      mostrar({ tono: 'exito', titulo: `Cuenta ${email} eliminada` });
      if (nueva?.cuenta.email === email) setNueva(null);
      await refrescar();
    },
    onError: (fallo) =>
      mostrar({ tono: 'error', titulo: 'No se pudo eliminar la cuenta', detalle: detalle(fallo) }),
  });

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (correo.trim()) crear.mutate();
  }

  const ocupado = regenerar.isPending || eliminar.isPending;

  return (
    <section className={estilos.seccion} aria-label="Cuentas de API">
      <h2 className={estilos.titulo}>Cuentas de API</h2>
      <p className={layout.textoSecundario}>
        Para programas (ELT, reportes, scripts): entran con correo y contraseña en{' '}
        <code>POST /api/v1/auth/token</code>, sin Google. Sire genera la contraseña, la
        muestra una sola vez y la cambia cuando vence o cuando la regeneras.
      </p>

      {nueva ? <ClaveNueva nueva={nueva} alCerrar={() => setNueva(null)} /> : null}

      <form className={estilos.formulario} onSubmit={alEnviar}>
        <TextField
          etiqueta="Correo de la cuenta"
          type="email"
          name="correo-api"
          value={correo}
          onChange={(evento) => setCorreo(evento.target.value)}
          placeholder="administrador@apaclla.au.pe"
          autoComplete="off"
          required
        />
        <SelectField
          etiqueta="Rol"
          name="rol-api"
          value={rol}
          onChange={(evento) => setRol(evento.target.value as RolUsuario)}
          opciones={ROLES}
        />
        <SelectField
          etiqueta="La contraseña vence en"
          name="vigencia-api"
          value={vigencia}
          onChange={(evento) => setVigencia(evento.target.value)}
          opciones={VIGENCIAS}
        />
        <div className={layout.filaFin}>
          <Button type="submit" variante="primario" pequeno cargando={crear.isPending}>
            Crear cuenta y generar contraseña
          </Button>
        </div>
      </form>

      {cuentas.isPending ? <Skeleton lineas={2} etiqueta="Cargando las cuentas de API" /> : null}
      {cuentas.isError ? (
        <ErrorState
          titulo="No se pudieron cargar las cuentas de API"
          texto={detalle(cuentas.error)}
          accion={
            <Button pequeno onClick={() => void cuentas.refetch()}>
              Reintentar
            </Button>
          }
        />
      ) : null}

      {cuentas.data?.length ? (
        <ul className={estilos.lista}>
          {cuentas.data.map((cuenta) => (
            <li key={cuenta.email} className={estilos.fila}>
              <span className={estilos.correo}>
                {cuenta.email}
                <br />
                <small className={layout.textoSecundario}>
                  {cuenta.vigente
                    ? `Vence el ${formatearFecha(cuenta.expira_en)}`
                    : 'Contraseña vencida'}
                  {' · '}
                  {cuenta.ultimo_uso_en
                    ? `Último uso: ${formatearFechaHora(cuenta.ultimo_uso_en)}`
                    : 'Sin usar'}
                </small>
              </span>
              <span className={layout.fila}>
                <Badge tono={cuenta.rol === 'admin' ? 'info' : 'neutro'}>
                  {cuenta.rol === 'admin' ? 'Admin' : 'Usuario'}
                </Badge>
                <Badge tono={cuenta.vigente ? 'exito' : 'error'}>
                  {cuenta.vigente ? 'Vigente' : 'Vencida'}
                </Badge>
              </span>
              <span className={layout.fila}>
                <Button
                  pequeno
                  variante="fantasma"
                  onClick={() => regenerar.mutate(cuenta.email)}
                  disabled={ocupado}
                >
                  Nueva contraseña
                </Button>
                <Button
                  pequeno
                  variante="peligro"
                  onClick={() => eliminar.mutate(cuenta.email)}
                  disabled={ocupado}
                  aria-label={`Eliminar la cuenta de API ${cuenta.email}`}
                >
                  Eliminar
                </Button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
