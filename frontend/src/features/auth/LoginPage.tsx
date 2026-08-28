import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';

import { Button } from '@/components/ui/Button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { TextField } from '@/components/ui/Field';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { ApiError } from '@/lib/http';
import { esRucValido } from '@/types/domain';

import estilos from './Acceso.module.css';
import { useAuth } from './useAuth';

interface EstadoRuta {
  desde?: string;
}

export function LoginPage() {
  useDocumentTitle('Iniciar sesión');

  const { iniciarSesion } = useAuth();
  const navegar = useNavigate();
  const ubicacion = useLocation();

  const [ruc, setRuc] = useState('');
  const [usuario, setUsuario] = useState('');
  const [password, setPassword] = useState('');
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
      await iniciarSesion({ ruc: ruc.trim(), usuario: usuario.trim(), password });
      const destino = (ubicacion.state as EstadoRuta | null)?.desde ?? '/';
      await navegar(destino, { replace: true });
    } catch (fallo) {
      setError(
        fallo instanceof ApiError
          ? fallo.message
          : 'No se pudo iniciar sesión. Inténtalo de nuevo.',
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className={estilos.pagina}>
      <div className={estilos.tarjeta}>
        <div className={estilos.encabezado}>
          <ThemeToggle />
        </div>
        <h1 className={`${estilos.titulo} ${estilos.tituloEspaciado}`}>Iniciar sesión</h1>

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
            autoComplete="username"
            maxLength={11}
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
            autoComplete="current-password"
            required
          />

          <Button type="submit" variante="primario" bloque cargando={enviando}>
            {enviando ? 'Verificando…' : 'Entrar'}
          </Button>
        </form>

        <p className={estilos.pie}>
          ¿La empresa aún no está registrada? <Link to="/registro">Darla de alta</Link>
        </p>
      </div>
    </main>
  );
}
