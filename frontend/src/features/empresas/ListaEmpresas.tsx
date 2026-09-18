import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import type { EmpresaResponse } from '@/types/api';

import estilos from './ListaEmpresas.module.css';

interface Props {
  empresas: readonly EmpresaResponse[];
  /** RUC activo, si ya hay uno. En la primera elección todavía no lo hay. */
  activo?: string | null;
  onElegir: (ruc: string) => void;
}

/**
 * Lista de empresas con filtro. Son `<button>` de verdad dentro de un `<ul>`:
 * la tabulación, el `Enter` y el rol de botón salen del navegador, sin ARIA
 * inventado. Un listbox a medida habría que sostenerlo con foco virtual y
 * `aria-activedescendant`, y axe no detecta un `tabindex` rotativo mal hecho:
 * los tests darían verde con algo inutilizable por teclado.
 *
 * Se usa en dos sitios: dentro del diálogo del selector y en línea, cuando
 * `EmpresaGate` pide elegir cuenta por primera vez.
 */
export function ListaEmpresas({ empresas, activo, onElegir }: Props) {
  const [filtro, setFiltro] = useState('');

  const visibles = useMemo(() => {
    const busqueda = filtro.trim().toLowerCase();
    if (!busqueda) return empresas;
    return empresas.filter((empresa) =>
      [empresa.ruc, empresa.nombre ?? '', empresa.rubro ?? '']
        .join(' ')
        .toLowerCase()
        .includes(busqueda),
    );
  }, [empresas, filtro]);

  return (
    <div className={estilos.contenedor}>
      {/* Con tres cuentas el filtro sobra; con trescientas es lo único que hace
          la lista usable, y no estorba en el primer caso. */}
      <TextField
        etiqueta="Filtrar por RUC, nombre o rubro"
        value={filtro}
        onChange={(evento) => setFiltro(evento.target.value)}
        autoComplete="off"
      />

      <p className="visually-hidden" role="status" aria-live="polite">
        {visibles.length === 1 ? '1 empresa coincide' : `${visibles.length} empresas coinciden`}
      </p>

      {visibles.length === 0 ? (
        <EmptyState titulo="Ninguna empresa coincide" texto="Prueba con otro RUC o nombre." />
      ) : (
        <ul className={estilos.lista}>
          {visibles.map((empresa) => {
            const esActiva = empresa.ruc === activo;
            const nombre = empresa.nombre?.trim();
            const rubro = empresa.rubro ?? 'Rubro no determinado';
            return (
              <li key={empresa.ruc}>
                <button
                  type="button"
                  className={estilos.opcion}
                  // `aria-current` marca la activa en el árbol accesible; la
                  // insignia la marca en palabras. El color nunca va solo.
                  aria-current={esActiva || undefined}
                  // Nombre accesible explícito: el contenido visible son dos
                  // líneas anidadas que se concatenarían en un orden confuso.
                  aria-label={`${nombre ? `${nombre}, ` : ''}RUC ${empresa.ruc}, ${rubro}${
                    esActiva ? ', empresa activa' : ''
                  }`}
                  onClick={() => onElegir(empresa.ruc)}
                >
                  <span className={estilos.textos}>
                    {/* Sin nombre, el RUC es el identificador: mejor eso que un
                        «Sin nombre» repetido en toda la lista. */}
                    <span className={nombre ? estilos.nombre : estilos.nombreMono}>
                      {nombre ?? empresa.ruc}
                    </span>
                    <span className={estilos.meta}>
                      {nombre ? <span className={estilos.ruc}>{empresa.ruc} · </span> : null}
                      {rubro}
                    </span>
                  </span>
                  {esActiva ? <Badge tono="info">Activa</Badge> : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
