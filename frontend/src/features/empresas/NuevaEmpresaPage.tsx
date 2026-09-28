import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { Button, ButtonLink } from '@/components/ui/Button';
import { guardarEmpresaActiva } from '@/lib/session';
import type { EmpresaCreada } from '@/types/api';

import { CargaMasiva } from './CargaMasiva';
import { FormularioNuevaEmpresa } from './FormularioNuevaEmpresa';
import { Marco } from './Marco';
import estilos from './NuevaEmpresaPage.module.css';
import { ResultadoCarga } from './ResultadoCarga';

type Modo = 'masiva' | 'individual';

/**
 * Alta de empresas, fuera del panel.
 *
 * No va dentro de `AppShell` aunque se llegue desde él: la barra lateral
 * anuncia la empresa **activa**, que aquí no es de la que se está hablando, y
 * la navegación lateral no tiene ninguna sección a la que corresponda esta
 * pantalla. Comparte marco con el gate, que es el otro sitio desde el que se
 * da de alta una empresa.
 *
 * Abre en la carga masiva: el contador llega con su cartera de empresas, y la
 * individual queda para la que se le escapó.
 *
 * Tras el alta individual la pantalla se queda mostrando cómo se completan el
 * token y el CIIU; hasta que terminan, la empresa existe pero todavía no puede
 * sincronizar con SUNAT.
 */
export function NuevaEmpresaPage() {
  const navegar = useNavigate();
  const cliente = useQueryClient();
  const [modo, setModo] = useState<Modo>('masiva');
  const [creada, setCreada] = useState<EmpresaCreada | null>(null);

  function entrar(ruc: string) {
    // Se entra directo a la cuenta recién creada: es lo que se venía a hacer,
    // y evita tener que buscarla en el selector.
    guardarEmpresaActiva(ruc);
    void navegar('/dashboard', { replace: true });
  }

  return (
    <Marco
      titulo="Registrar empresas"
      ancho="amplio"
      intro="La contraseña SOL se guarda cifrada de forma reversible, porque el sistema la necesita en claro para autenticarse contra SUNAT en tu nombre. Al registrar, se obtienen solos el CIIU y el rubro de cada empresa."
      pie={
        <ButtonLink a="/" variante="fantasma" pequeno>
          Volver al panel
        </ButtonLink>
      }
    >
      <div className={estilos.modos} role="group" aria-label="Modalidad de registro">
        {(['masiva', 'individual'] as const).map((opcion) => (
          <Button
            key={opcion}
            variante={modo === opcion ? 'primario' : 'secundario'}
            pequeno
            aria-pressed={modo === opcion}
            onClick={() => {
              setModo(opcion);
              setCreada(null);
            }}
          >
            {opcion === 'masiva' ? 'Carga masiva' : 'Individual'}
          </Button>
        ))}
      </div>

      {modo === 'masiva' ? <CargaMasiva /> : null}

      {modo === 'individual' && creada ? (
        <ResultadoCarga
          cargaId={creada.carga_id}
          onTerminada={() => {
            void cliente.invalidateQueries({ queryKey: ['empresas'] });
          }}
          accion={
            <Button variante="primario" onClick={() => entrar(creada.ruc)}>
              Entrar a la empresa
            </Button>
          }
        />
      ) : null}

      {modo === 'individual' && !creada ? (
        <FormularioNuevaEmpresa
          onCreada={(empresa) => {
            // El gate tiene la lista cacheada y es quien la va a releer al volver.
            void cliente.invalidateQueries({ queryKey: ['empresas'] });
            setCreada(empresa);
          }}
        />
      ) : null}
    </Marco>
  );
}
