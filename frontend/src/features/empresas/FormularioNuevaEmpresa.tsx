import { useState } from 'react';
import type { FormEvent } from 'react';

import { crearEmpresa } from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';
import { ApiError } from '@/lib/http';
import type { EmpresaResponse } from '@/types/api';
import { esRucValido } from '@/types/domain';

import estilos from './FormularioNuevaEmpresa.module.css';

interface Props {
  /** Qué hacer con la empresa recién creada. El formulario no navega por su cuenta. */
  onCreada: (empresa: EmpresaResponse) => void;
}

/**
 * Alta de empresa. Vive como componente y no como pantalla porque se usa en dos
 * sitios: la ruta `/empresas/nueva` del panel y el estado vacío de
 * `EmpresaGate`. Ese segundo caso es el que obliga a separarlo — cuando no hay
 * ninguna empresa todavía no se puede entrar al panel, así que el formulario
 * tiene que poder pintarse fuera de él.
 */
export function FormularioNuevaEmpresa({ onCreada }: Props) {
  const [ruc, setRuc] = useState('');
  const [nombre, setNombre] = useState('');
  const [usuario, setUsuario] = useState('');
  const [password, setPassword] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');

  const [errorRuc, setErrorRuc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setError(null);

    if (!esRucValido(ruc)) {
      setErrorRuc('El RUC debe tener 11 dígitos.');
      return;
    }
    setErrorRuc(null);
    setEnviando(true);

    try {
      const creada = await crearEmpresa({
        ruc: ruc.trim(),
        usuario: usuario.trim(),
        password,
        // Solo se envían si se completaron: el backend acepta que falten y cae
        // a las credenciales globales de respaldo.
        ...(nombre.trim() ? { nombre: nombre.trim() } : {}),
        ...(clientId.trim() ? { sunat_client_id: clientId.trim() } : {}),
        ...(clientSecret.trim() ? { sunat_client_secret: clientSecret.trim() } : {}),
      });
      onCreada(creada);
    } catch (fallo) {
      if (fallo instanceof ApiError && fallo.esConflicto) {
        setError('Ese RUC ya está registrado; búscalo en el selector de empresas.');
      } else if (fallo instanceof ApiError) {
        setError(fallo.message);
      } else {
        setError('No se pudo registrar la empresa. Inténtalo de nuevo.');
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className={estilos.formulario} onSubmit={(evento) => void alEnviar(evento)} noValidate>
      {error ? (
        <p className={estilos.aviso} role="alert">
          {error}
        </p>
      ) : null}

      <TextField
        etiqueta="RUC"
        name="ruc"
        value={ruc}
        onChange={(evento) => setRuc(evento.target.value)}
        inputMode="numeric"
        maxLength={11}
        autoComplete="off"
        required
        mono
        error={errorRuc}
        ayuda="11 dígitos, sin espacios ni guiones."
      />

      <TextField
        etiqueta="Nombre"
        name="nombre"
        value={nombre}
        onChange={(evento) => setNombre(evento.target.value)}
        autoComplete="off"
        ayuda="Opcional. Es lo que verás en el selector de cuentas, en vez del RUC."
      />

      <TextField
        etiqueta="Usuario SOL"
        name="usuario"
        value={usuario}
        onChange={(evento) => setUsuario(evento.target.value)}
        autoComplete="off"
        required
      />

      <TextField
        etiqueta="Contraseña SOL"
        name="password"
        type="password"
        value={password}
        onChange={(evento) => setPassword(evento.target.value)}
        autoComplete="new-password"
        required
      />

      <details className={estilos.opcionales}>
        <summary className={estilos.resumen}>
          Credenciales propias de la API SIRE (opcional)
        </summary>
        <div className={estilos.detalleCuerpo}>
          <TextField
            etiqueta="Client ID de SUNAT"
            name="sunat_client_id"
            value={clientId}
            onChange={(evento) => setClientId(evento.target.value)}
            autoComplete="off"
            mono
            ayuda="Si lo dejas vacío se usan las credenciales globales del servidor."
          />
          <TextField
            etiqueta="Client Secret de SUNAT"
            name="sunat_client_secret"
            type="password"
            value={clientSecret}
            onChange={(evento) => setClientSecret(evento.target.value)}
            autoComplete="off"
          />
        </div>
      </details>

      <Button type="submit" variante="primario" bloque cargando={enviando}>
        {enviando ? 'Registrando…' : 'Registrar empresa'}
      </Button>
    </form>
  );
}
