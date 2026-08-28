import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';

import { crearEmpresa } from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { TextField } from '@/components/ui/Field';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/lib/http';
import { esRucValido } from '@/types/domain';

import estilos from './Acceso.module.css';

export function RegistroPage() {
  useDocumentTitle('Registrar empresa');

  const navegar = useNavigate();

  const [ruc, setRuc] = useState('');
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
      await crearEmpresa({
        ruc: ruc.trim(),
        usuario: usuario.trim(),
        password,
        // Solo se envían si el usuario los completó: el backend acepta que
        // falten y cae a las credenciales globales de respaldo.
        ...(clientId.trim() ? { sunat_client_id: clientId.trim() } : {}),
        ...(clientSecret.trim() ? { sunat_client_secret: clientSecret.trim() } : {}),
      });
      await navegar('/login', { replace: true });
    } catch (fallo) {
      if (fallo instanceof ApiError && fallo.esConflicto) {
        setError('Ese RUC ya está registrado. Inicia sesión en su lugar.');
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
    <main className={estilos.pagina}>
      <div className={estilos.tarjeta}>
        <div className={estilos.encabezado}>
          <p className={estilos.marca}>Sire · SUNAT</p>
          <ThemeToggle />
        </div>
        <h1 className={estilos.titulo}>Registrar empresa</h1>
        <p className={estilos.intro}>
          La contraseña SOL se guarda cifrada de forma reversible, porque el sistema la necesita
          en claro para autenticarse contra SUNAT en tu nombre.
        </p>

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

        <p className={estilos.pie}>
          ¿Ya está registrada? <Link to="/login">Iniciar sesión</Link>
        </p>
      </div>
    </main>
  );
}
