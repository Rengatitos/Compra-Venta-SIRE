import { pedir, segmento } from '@/lib/http';
import type {
  ActividadEconomica,
  ClaseCiiu,
  CodigoVinculacion,
  EmpresaCreate,
  EmpresaResponse,
  EmpresaUpdate,
  MessageResponse,
  StatusResponse,
} from '@/types/api';

const base = (ruc: string) => `/empresas/${segmento(ruc)}`;

/**
 * `GET /api/v1/empresas`. Todas las empresas registradas; es lo que alimenta el
 * selector de cuentas. Ya no exige el token de administrador: va con el JWT de
 * la persona, que tiene acceso a todas.
 */
export function listarEmpresas(): Promise<EmpresaResponse[]> {
  return pedir<EmpresaResponse[]>('/empresas');
}

/** `POST /api/v1/empresas`. Alta de empresa. Requiere sesión. Límite 5/min. */
export function crearEmpresa(datos: EmpresaCreate): Promise<EmpresaResponse> {
  return pedir<EmpresaResponse>('/empresas', { metodo: 'POST', cuerpo: datos });
}

export function obtenerEmpresa(ruc: string): Promise<EmpresaResponse> {
  return pedir<EmpresaResponse>(base(ruc));
}

/**
 * `PUT /api/v1/empresas/{ruc}`. Solo se envían las claves con valor: para el
 * backend, un `sunat_client_id` vacío significa "no lo toques", no "bórralo".
 */
export function actualizarEmpresa(ruc: string, datos: EmpresaUpdate): Promise<EmpresaResponse> {
  const cuerpo: EmpresaUpdate = {};
  for (const [clave, valor] of Object.entries(datos)) {
    if (typeof valor === 'string' && valor.trim() !== '') {
      cuerpo[clave as keyof EmpresaUpdate] = valor.trim();
    }
  }
  return pedir<EmpresaResponse>(base(ruc), { metodo: 'PUT', cuerpo });
}

/**
 * Guarda las actividades económicas y cuál manda al clasificar. Va aparte de
 * `actualizarEmpresa`, que solo envía textos no vacíos.
 */
export function guardarActividades(
  ruc: string,
  actividades: ActividadEconomica[],
  ciiuPrincipal: string | null,
): Promise<EmpresaResponse> {
  return pedir<EmpresaResponse>(base(ruc), {
    metodo: 'PUT',
    cuerpo: {
      actividades_economicas: actividades,
      ciiu_principal_clasificacion: ciiuPrincipal,
    },
  });
}

/** Catálogo CIIU Rev. 4: por código o por palabras del título. */
export function buscarCiiu(consulta: string): Promise<ClaseCiiu[]> {
  return pedir<ClaseCiiu[]>('/ciiu', { consulta: { q: consulta } });
}

/** Borra en cascada comprobantes, periodos y plan de cuentas de la empresa. */
export function eliminarEmpresa(ruc: string): Promise<MessageResponse> {
  return pedir<MessageResponse>(base(ruc), { metodo: 'DELETE' });
}

/**
 * `POST …/ficha-ruc`. Obtiene el CIIU de la empresa: consulta su ficha en la
 * Consulta RUC de SUNAT y guarda sus actividades económicas, que el
 * clasificador contable usa como contexto. Tarda unos segundos.
 */
export function obtenerCiiuEmpresa(ruc: string): Promise<EmpresaResponse> {
  return pedir<EmpresaResponse>(`${base(ruc)}/ficha-ruc`, { metodo: 'POST' });
}

/** `POST …/token-sunat`. Fuerza un OAuth nuevo contra la API SIRE. */
export function renovarTokenSunat(ruc: string): Promise<StatusResponse> {
  return pedir<StatusResponse>(`${base(ruc)}/token-sunat`, { metodo: 'POST' });
}

/**
 * `POST …/codigos-vinculacion`. Código de 6 dígitos para vincular Apaclla Bot
 * con la empresa. Vive 10 minutos, sirve una vez y anula los anteriores.
 */
export function generarCodigoVinculacion(ruc: string): Promise<CodigoVinculacion> {
  return pedir<CodigoVinculacion>(`${base(ruc)}/codigos-vinculacion`, { metodo: 'POST' });
}
