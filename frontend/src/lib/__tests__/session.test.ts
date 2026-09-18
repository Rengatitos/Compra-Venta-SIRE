import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  guardarEmpresaActiva,
  guardarSesion,
  limpiarSesion,
  obtenerSesion,
  obtenerToken,
  suscribirSesion,
} from '../session';

const SESION = {
  token: 'jwt-de-prueba',
  correo: 'prueba@example.com',
  nombre: 'Prueba',
  ruc: null,
};

describe('sesión', () => {
  afterEach(() => {
    limpiarSesion();
    vi.restoreAllMocks();
  });

  it('guarda y devuelve la identidad de la persona', () => {
    guardarSesion(SESION);

    expect(obtenerSesion()).toEqual(SESION);
    expect(obtenerToken()).toBe('jwt-de-prueba');
  });

  it('cambiar de empresa no toca el resto de la sesión', () => {
    // Es el punto de toda la pantalla: elegir otra cuenta no es volver a
    // autenticarse.
    guardarSesion(SESION);

    guardarEmpresaActiva('20603391692');

    expect(obtenerSesion()).toEqual({ ...SESION, ruc: '20603391692' });
    expect(obtenerToken()).toBe('jwt-de-prueba');
  });

  it('avisa a los oyentes al cambiar de empresa', () => {
    guardarSesion(SESION);
    const oyente = vi.fn();
    const cancelar = suscribirSesion(oyente);

    guardarEmpresaActiva('20603391692');

    expect(oyente).toHaveBeenCalledWith({ ...SESION, ruc: '20603391692' });
    cancelar();
  });

  it('sin sesión, elegir empresa no crea una a medias', () => {
    guardarEmpresaActiva('20603391692');

    expect(obtenerSesion()).toBeNull();
  });

  it('al arrancar lee una sesión válida del almacén', async () => {
    // Contraparte del test siguiente: si este no pasara, aquel pasaría solo
    // porque el módulo no se está releyendo.
    sessionStorage.setItem('sire.sesion', JSON.stringify(SESION));
    vi.resetModules();

    const modulo = await import('../session');

    expect(modulo.obtenerSesion()).toEqual(SESION);
    sessionStorage.clear();
  });

  it('una sesión del esquema anterior se descarta', async () => {
    // `{token, ruc}` sin correo es la forma vieja: su JWT identificaba a una
    // empresa y el backend ya no lo acepta, así que lo correcto es mandar a la
    // persona a iniciar sesión en vez de dejar la interfaz llena de 401.
    sessionStorage.setItem('sire.sesion', JSON.stringify({ token: 'viejo', ruc: '20603391692' }));
    vi.resetModules();

    const modulo = await import('../session');

    expect(modulo.obtenerSesion()).toBeNull();
    sessionStorage.clear();
  });

  it('con el almacenamiento bloqueado la sesión sigue viva en memoria', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('modo privado');
    });

    guardarSesion(SESION);

    expect(obtenerSesion()).toEqual(SESION);
  });
});
