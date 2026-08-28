import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, pedir } from '../http';
import { guardarSesion, limpiarSesion } from '../session';

function respuestaJson(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('pedir', () => {
  beforeEach(() => {
    limpiarSesion();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    limpiarSesion();
  });

  it('añade la cabecera Bearer cuando hay sesión', async () => {
    const espia = vi.fn().mockResolvedValue(respuestaJson({ periodo: '202606' }));
    vi.stubGlobal('fetch', espia);
    guardarSesion({ token: 'jwt-de-prueba', ruc: '20608997106' });

    await pedir('/empresas/20608997106/periodos/202606');

    const [, init] = espia.mock.calls[0] as [string, RequestInit];
    const cabeceras = init.headers as Headers;
    expect(cabeceras.get('Authorization')).toBe('Bearer jwt-de-prueba');
  });

  it('omite los parámetros vacíos al construir la consulta', async () => {
    const espia = vi.fn().mockResolvedValue(respuestaJson([]));
    vi.stubGlobal('fetch', espia);

    await pedir('/comprobantes', { consulta: { limit: 100, libro: undefined, skip: 0 } });

    const [url] = espia.mock.calls[0] as [string];
    expect(url).toContain('limit=100');
    expect(url).toContain('skip=0');
    expect(url).not.toContain('libro');
  });

  it('convierte el detail de FastAPI en el mensaje del ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(respuestaJson({ detail: 'El periodo ya existe' }, 409)),
    );

    await expect(pedir('/periodos', { metodo: 'POST' })).rejects.toMatchObject({
      status: 409,
      message: 'El periodo ya existe',
    });
  });

  it('junta los mensajes de un error de validación de Pydantic', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        respuestaJson(
          { detail: [{ msg: 'El RUC debe tener 11 dígitos' }, { msg: 'Campo requerido' }] },
          422,
        ),
      ),
    );

    await expect(pedir('/empresas', { metodo: 'POST' })).rejects.toThrow(
      'El RUC debe tener 11 dígitos. Campo requerido',
    );
  });

  it('limpia la sesión ante un 401, porque el JWT solo dura dos horas', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuestaJson({ detail: 'Token expirado' }, 401)));
    guardarSesion({ token: 'caducado', ruc: '20608997106' });

    await expect(pedir('/empresas/20608997106')).rejects.toBeInstanceOf(ApiError);

    const segunda = vi.fn().mockResolvedValue(respuestaJson({}));
    vi.stubGlobal('fetch', segunda);
    await pedir('/health');

    const [, init] = segunda.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Headers).has('Authorization')).toBe(false);
  });

  it('traduce un fallo de red en un ApiError con status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    await expect(pedir('/health')).rejects.toMatchObject({ status: 0 });
  });

  it('usa un mensaje de respaldo cuando la respuesta de error no trae JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>502</html>', { status: 502 })),
    );

    await expect(pedir('/analytics/summary')).rejects.toThrow(/SUNAT no respondió/);
  });
});
