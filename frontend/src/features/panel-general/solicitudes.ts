import type { TonoInsignia } from '@/components/ui/Badge';
import { formatearFechaHora } from '@/lib/format';
import type { PasoSolicitudResponse } from '@/types/api';
import type {
  EstadoEnvio,
  EstadoItemSolicitud,
  EstadoSolicitud,
  PasoSolicitud,
} from '@/types/domain';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
}

/** `app/domain/solicitudes.py::EstadoSolicitud`. */
const SOLICITUD: Record<EstadoSolicitud, Presentacion> = {
  en_progreso: { tono: 'info', texto: 'En proceso' },
  empaquetando: { tono: 'info', texto: 'Generando archivos' },
  enviando: { tono: 'info', texto: 'Enviando correos' },
  completada: { tono: 'exito', texto: 'Completada' },
  completada_con_errores: { tono: 'aviso', texto: 'Completada con errores' },
  fallida: { tono: 'error', texto: 'Con error' },
};

const ITEM: Record<EstadoItemSolicitud, Presentacion> = {
  pendiente: { tono: 'neutro', texto: 'Pendiente' },
  en_progreso: { tono: 'info', texto: 'En proceso' },
  completado: { tono: 'exito', texto: 'Completado' },
  con_errores: { tono: 'aviso', texto: 'Con observaciones' },
  fallido: { tono: 'error', texto: 'Con error' },
};

const ENVIO: Record<EstadoEnvio, Presentacion> = {
  pendiente: { tono: 'neutro', texto: 'Pendiente' },
  enviado: { tono: 'exito', texto: 'Enviado' },
  fallido: { tono: 'error', texto: 'Fallido' },
  bloqueado: { tono: 'neutro', texto: 'No permitido en este entorno' },
};

export const ETIQUETA_PASO: Record<PasoSolicitud, string> = {
  credenciales: 'Credenciales',
  sire_compras: 'SIRE compras',
  sire_ventas: 'SIRE ventas',
  detalle_compras: 'Comprobantes de compras',
  detalle_ventas: 'Comprobantes de ventas',
  clasificacion_compras: 'IA compras',
  clasificacion_ventas: 'IA ventas',
};

export function presentarSolicitud(estado: EstadoSolicitud): Presentacion {
  return SOLICITUD[estado] ?? { tono: 'neutro', texto: estado };
}

export function presentarItem(estado: EstadoItemSolicitud): Presentacion {
  return ITEM[estado] ?? { tono: 'neutro', texto: estado };
}

export function presentarEnvio(estado: EstadoEnvio): Presentacion {
  return ENVIO[estado] ?? { tono: 'neutro', texto: estado };
}

/**
 * El estado de un paso tal como lo vive el contador: un paso «encolado» puede
 * estar esperando turno, corriendo o esperando un reintento, y eso sale del
 * job que lo ejecuta.
 */
export function presentarPaso(paso: PasoSolicitudResponse): Presentacion {
  switch (paso.estado) {
    case 'completado':
      return { tono: 'exito', texto: 'Completado' };
    case 'fallido':
      return { tono: 'error', texto: 'Fallido' };
    case 'omitido':
      return { tono: 'neutro', texto: 'Omitido' };
    case 'pendiente':
      return { tono: 'neutro', texto: 'Pendiente' };
    case 'encolado': {
      if (paso.job_estado === 'en_progreso') return { tono: 'info', texto: 'En curso' };
      const intentos = paso.intentos ?? 0;
      if (intentos > 0) {
        const cuando = paso.siguiente_intento_en
          ? `, ${formatearFechaHora(paso.siguiente_intento_en)}`
          : '';
        return {
          tono: 'aviso',
          texto: `Reintento ${intentos + 1} de ${paso.max_intentos ?? intentos + 1}${cuando}`,
        };
      }
      return { tono: 'neutro', texto: 'En cola' };
    }
    default:
      return { tono: 'neutro', texto: paso.estado };
  }
}

/** Periodos `YYYYMM` entre dos meses `YYYY-MM` (los de un `<input type="month">`). */
export function periodosEntre(desde: string, hasta: string, maximo = 36): string[] {
  const inicio = /^(\d{4})-(\d{2})$/.exec(desde);
  const fin = /^(\d{4})-(\d{2})$/.exec(hasta);
  if (!inicio || !fin) return [];
  let anio = Number(inicio[1]);
  let mes = Number(inicio[2]);
  const ultimo = Number(fin[1]) * 12 + Number(fin[2]);
  const periodos: string[] = [];
  while (anio * 12 + mes <= ultimo && periodos.length < maximo) {
    periodos.push(`${anio}${String(mes).padStart(2, '0')}`);
    mes += 1;
    if (mes > 12) {
      mes = 1;
      anio += 1;
    }
  }
  return periodos;
}

/** El mes actual como `YYYY-MM`, en hora local. */
export function mesActual(ahora = new Date()): string {
  return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, '0')}`;
}
