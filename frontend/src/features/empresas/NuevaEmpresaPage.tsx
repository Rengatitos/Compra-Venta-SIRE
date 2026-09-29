import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { obtenerCarga } from '@/api/empresas';
import { Button, ButtonLink } from '@/components/ui/Button';
import { formatearFechaHora } from '@/lib/format';
import { guardarEmpresaActiva } from '@/lib/session';
import type { EmpresaCreada } from '@/types/api';

import { CargaMasiva } from './CargaMasiva';
import { describirCarga } from './cargas';
import { FormularioNuevaEmpresa } from './FormularioNuevaEmpresa';
import { IngresosAnteriores } from './IngresosAnteriores';
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
 *
 * «Ver ingresos anteriores» lista cada registro ya hecho con su fecha, su
 * avance y su reporte: salir de la pantalla no los pierde.
 */
export function NuevaEmpresaPage() {
  const navegar = useNavigate();
  const cliente = useQueryClient();
  const [modo, setModo] = useState<Modo>('masiva');
  const [creada, setCreada] = useState<EmpresaCreada | null>(null);
  // Los ingresos anteriores van en la URL (`?vista=anteriores`, `?carga=<id>`)
  // para que recargar o volver con «Atrás» no pierda el reporte que se miraba.
  const [parametros, setParametros] = useSearchParams();
  const cargaAbierta = parametros.get('carga');
  const verAnteriores = parametros.get('vista') === 'anteriores' || cargaAbierta !== null;

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
      <div className={estilos.barra}>
        <div className={estilos.modos} role="group" aria-label="Modalidad de registro">
          {(['masiva', 'individual'] as const).map((opcion) => {
            const activo = !verAnteriores && modo === opcion;
            return (
              <Button
                key={opcion}
                variante={activo ? 'primario' : 'secundario'}
                pequeno
                aria-pressed={activo}
                onClick={() => {
                  setModo(opcion);
                  setCreada(null);
                  setParametros({});
                }}
              >
                {opcion === 'masiva' ? 'Carga masiva' : 'Individual'}
              </Button>
            );
          })}
        </div>
        <Button
          variante={verAnteriores ? 'primario' : 'fantasma'}
          pequeno
          aria-pressed={verAnteriores}
          icono={
            <svg className={estilos.icono} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <circle cx="12" cy="12" r="8.25" />
              <path d="M12 7.5V12l3 2" />
            </svg>
          }
          onClick={() => setParametros({ vista: 'anteriores' })}
        >
          Ver ingresos anteriores
        </Button>
      </div>

      {verAnteriores && cargaAbierta ? (
        <DetalleIngreso
          cargaId={cargaAbierta}
          onVolver={() => setParametros({ vista: 'anteriores' })}
        />
      ) : null}

      {verAnteriores && !cargaAbierta ? (
        <IngresosAnteriores onAbrir={(id) => setParametros({ carga: id })} />
      ) : null}

      {!verAnteriores && modo === 'masiva' ? <CargaMasiva /> : null}

      {!verAnteriores && modo === 'individual' && creada ? (
        <ResultadoCarga
          cargaId={creada.carga_id}
          onTerminada={() => {
            void cliente.invalidateQueries({ queryKey: ['empresas'] });
            void cliente.invalidateQueries({ queryKey: ['cargas-empresas'] });
          }}
          accion={
            <Button variante="primario" onClick={() => entrar(creada.ruc)}>
              Entrar a la empresa
            </Button>
          }
        />
      ) : null}

      {!verAnteriores && modo === 'individual' && !creada ? (
        <FormularioNuevaEmpresa
          onCreada={(empresa) => {
            // El gate tiene la lista cacheada y es quien la va a releer al volver.
            void cliente.invalidateQueries({ queryKey: ['empresas'] });
            void cliente.invalidateQueries({ queryKey: ['cargas-empresas'] });
            setCreada(empresa);
          }}
        />
      ) : null}
    </Marco>
  );
}

/** Un ingreso anterior: cuándo se hizo y su reporte (o su avance, si sigue). */
function DetalleIngreso({ cargaId, onVolver }: { cargaId: string; onVolver: () => void }) {
  const cliente = useQueryClient();
  // Misma clave que `ResultadoCarga`: comparten la consulta y su sondeo.
  const carga = useQuery({
    queryKey: ['carga-empresas', cargaId],
    queryFn: () => obtenerCarga(cargaId),
  });

  return (
    <div className={estilos.detalle}>
      <div className={estilos.cabeceraDetalle}>
        <Button variante="fantasma" pequeno onClick={onVolver}>
          ← Ingresos anteriores
        </Button>
        {carga.data ? (
          <p className={estilos.cuando}>
            <strong>Ingreso del {formatearFechaHora(carga.data.creado_en)}</strong>
            <span>
              {describirCarga(carga.data)} · por {carga.data.registrado_por}
              {carga.data.terminado_en
                ? ` · terminó el ${formatearFechaHora(carga.data.terminado_en)}`
                : ''}
            </span>
          </p>
        ) : null}
      </div>
      <ResultadoCarga
        cargaId={cargaId}
        onTerminada={() => {
          void cliente.invalidateQueries({ queryKey: ['empresas'] });
          void cliente.invalidateQueries({ queryKey: ['cargas-empresas'] });
        }}
      />
    </div>
  );
}
