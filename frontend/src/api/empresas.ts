import { descargar, enviarFormulario, pedir, segmento } from '@/lib/http';
import type {
  ActividadEconomica,
  CargaAceptada,
  CargaEmpresas,
  CargaResumen,
  ClaseCiiu,
  CodigoVinculacion,
  CredencialesSunatResultado,
  EmpresaCreada,
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

/**
 * `POST /api/v1/empresas`. Alta individual. Requiere sesión. Límite 5/min.
 * Responde en cuanto la empresa existe; el token y el CIIU se completan en la
 * cola y se siguen con `obtenerCarga(carga_id)`.
 */
export function crearEmpresa(datos: EmpresaCreate): Promise<EmpresaCreada> {
  return pedir<EmpresaCreada>('/empresas', { metodo: 'POST', cuerpo: datos });
}

/**
 * `POST /api/v1/empresas/cargas`. Excel con razón social, RUC, usuario y
 * contraseña SOL en las columnas A a D. Límite 3/min y 2 MB.
 */
export function cargarEmpresas(archivo: File): Promise<CargaAceptada> {
  const datos = new FormData();
  datos.append('archivo', archivo);
  return enviarFormulario<CargaAceptada>('/empresas/cargas', datos);
}

/** `GET /api/v1/empresas/cargas/{id}`: estado, progreso y resultado por fila. */
export function obtenerCarga(cargaId: string): Promise<CargaEmpresas> {
  return pedir<CargaEmpresas>(`/empresas/cargas/${segmento(cargaId)}`);
}

/** `GET /api/v1/empresas/cargas`: historial de altas, sin las filas. */
export function listarCargas(): Promise<CargaResumen[]> {
  return pedir<CargaResumen[]>('/empresas/cargas');
}

export function descargarReporteCarga(cargaId: string): Promise<void> {
  return descargar(`/empresas/cargas/${segmento(cargaId)}/reporte`, 'reporte_carga.xlsx');
}

export function descargarPlantillaCarga(): Promise<void> {
  return descargar('/empresas/cargas/plantilla', 'plantilla_empresas.xlsx');
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
 * `POST /api/v1/empresas/{ruc}/credenciales-sunat`. Entra a SOL con el usuario y
 * la clave guardados y trae el client_id y la clave del API SUNAT; si la empresa
 * no tiene aplicación, la registra. Tarda lo que un login SOL (≈1 min). La
 * clave nunca vuelve: se guarda en la empresa.
 */
export function obtenerCredencialesSunat(ruc: string): Promise<CredencialesSunatResultado> {
  return pedir<CredencialesSunatResultado>(`${base(ruc)}/credenciales-sunat`, {
    metodo: 'POST',
  });
}

/**
 * `POST …/codigos-vinculacion`. Código de 6 dígitos para vincular Apaclla Bot
 * con la empresa. Vive 10 minutos, sirve una vez y anula los anteriores.
 */
export function generarCodigoVinculacion(ruc: string): Promise<CodigoVinculacion> {
  return pedir<CodigoVinculacion>(`${base(ruc)}/codigos-vinculacion`, { metodo: 'POST' });
}
