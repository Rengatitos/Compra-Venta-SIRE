import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';

import { ButtonLink } from '@/components/ui/Button';
import { useToast } from '@/hooks/useToast';
import { guardarEmpresaActiva } from '@/lib/session';

import { FormularioNuevaEmpresa } from './FormularioNuevaEmpresa';
import { Marco } from './Marco';

/**
 * Alta de empresa, fuera del panel.
 *
 * No va dentro de `AppShell` aunque se llegue desde él: la barra lateral
 * anuncia la empresa **activa**, que aquí no es de la que se está hablando, y
 * la navegación lateral no tiene ninguna sección a la que corresponda esta
 * pantalla. Comparte marco con el gate, que es el otro sitio desde el que se
 * da de alta una empresa.
 */
export function NuevaEmpresaPage() {
  const navegar = useNavigate();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  return (
    <Marco
      titulo="Registrar empresa"
      intro="La contraseña SOL se guarda cifrada de forma reversible, porque el sistema la necesita en claro para autenticarse contra SUNAT en tu nombre."
      pie={
        <ButtonLink a="/" variante="fantasma" pequeno>
          Volver al panel
        </ButtonLink>
      }
    >
      <FormularioNuevaEmpresa
        onCreada={(empresa) => {
          // El gate tiene la lista cacheada y es quien la va a releer al volver.
          void cliente.invalidateQueries({ queryKey: ['empresas'] });
          // Se entra directo a la cuenta recién creada: es lo que se venía a
          // hacer, y evita tener que buscarla en el selector.
          guardarEmpresaActiva(empresa.ruc);
          mostrar({ tono: 'exito', titulo: 'Empresa registrada' });
          void navegar('/', { replace: true });
        }}
      />
    </Marco>
  );
}
