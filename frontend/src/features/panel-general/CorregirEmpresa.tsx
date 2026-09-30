import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import {
  actualizarEmpresa,
  crearEmpresa,
  eliminarEmpresa,
  obtenerCredencialesSunat,
  obtenerEmpresa,
} from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { TextField } from '@/components/ui/Field';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ResumenEmpresa } from '@/types/api';
import { esRucValido } from '@/types/domain';

import estilos from './EmpresasPage.module.css';

interface Props {
  empresa: ResumenEmpresa;
  onCerrar: () => void;
}

/**
 * Corrige el RUC, el usuario o la clave SOL de una empresa cuyo alta no obtuvo
 * las credenciales del API SUNAT, y vuelve a intentarlo.
 *
 * El RUC identifica a la empresa, así que cambiarlo es darla de alta con el
 * nuevo y borrar la mal escrita (primero el alta: si el RUC nuevo falla, la
 * original sigue ahí).
 */
export function CorregirEmpresa({ empresa, onCerrar }: Props) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const actual = useQuery({
    queryKey: ['empresa', empresa.ruc],
    queryFn: () => obtenerEmpresa(empresa.ruc),
  });
  const [ruc, setRuc] = useState(empresa.ruc);
  const [usuario, setUsuario] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [errorRuc, setErrorRuc] = useState<string | null>(null);

  const usuarioFinal = (usuario ?? actual.data?.usuario ?? '').trim();

  const reintentar = useMutation({
    mutationFn: async () => {
      const nuevo = ruc.trim();
      if (nuevo !== empresa.ruc) {
        await crearEmpresa({
          ruc: nuevo,
          nombre: empresa.nombre ?? undefined,
          usuario: usuarioFinal,
          password,
        });
        await eliminarEmpresa(empresa.ruc);
      } else {
        await actualizarEmpresa(empresa.ruc, { usuario: usuarioFinal, password });
      }
      return obtenerCredencialesSunat(nuevo);
    },
    onSuccess: async (resultado) => {
      mostrar({
        tono: 'exito',
        titulo: 'Empresa corregida: ya se puede abrir',
        detalle: resultado.mensaje,
      });
      await cliente.invalidateQueries({ queryKey: ['resumen-empresas'] });
      await cliente.invalidateQueries({ queryKey: ['empresas'] });
      onCerrar();
    },
    onError: async (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'SUNAT todavía no entrega las credenciales',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
      // Si el RUC ya se cambió, la lista tiene que reflejarlo aunque SOL falle.
      await cliente.invalidateQueries({ queryKey: ['resumen-empresas'] });
    },
  });

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!esRucValido(ruc.trim())) {
      setErrorRuc('RUC inválido: revisa los 11 dígitos y el dígito verificador.');
      return;
    }
    setErrorRuc(null);
    reintentar.mutate();
  }

  const listo = Boolean(ruc.trim() && usuarioFinal && password);

  return (
    <Dialog
      abierto
      titulo={`Corregir ${empresa.nombre ?? empresa.ruc}`}
      texto="Revisa los datos de SOL y vuelve a intentarlo. Sire entrará a SUNAT para traer las credenciales del API; tarda cerca de un minuto."
      onCerrar={reintentar.isPending ? () => undefined : onCerrar}
      acciones={
        <>
          <Button variante="fantasma" onClick={onCerrar} disabled={reintentar.isPending}>
            Cancelar
          </Button>
          <Button
            type="submit"
            form="form-corregir-empresa"
            variante="primario"
            cargando={reintentar.isPending}
            disabled={!listo}
          >
            {reintentar.isPending ? 'Entrando a SOL…' : 'Guardar y reintentar'}
          </Button>
        </>
      }
    >
      <form id="form-corregir-empresa" className={layout.pila} onSubmit={alEnviar} noValidate>
        {empresa.motivo_alta ? <p className={estilos.motivo}>{empresa.motivo_alta}</p> : null}
        <TextField
          etiqueta="RUC"
          name="ruc"
          inputMode="numeric"
          maxLength={11}
          mono
          value={ruc}
          onChange={(e) => setRuc(e.target.value.replace(/\D/g, ''))}
          error={errorRuc}
          autoComplete="off"
        />
        <TextField
          etiqueta="Usuario SOL"
          name="usuario"
          value={usuario ?? actual.data?.usuario ?? ''}
          onChange={(e) => setUsuario(e.target.value)}
          autoComplete="off"
        />
        <TextField
          etiqueta="Clave SOL"
          name="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          ayuda="Escríbela de nuevo aunque no haya cambiado."
        />
      </form>
    </Dialog>
  );
}
