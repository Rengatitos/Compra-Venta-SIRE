import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  alternarTema,
  establecerTema,
  obtenerTema,
  suscribirTema,
  TEMA_POR_DEFECTO,
} from '../theme';

describe('tema', () => {
  beforeEach(() => {
    localStorage.clear();
    establecerTema(TEMA_POR_DEFECTO);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('arranca en claro, que es el predeterminado del producto', () => {
    expect(TEMA_POR_DEFECTO).toBe('light');
    expect(obtenerTema()).toBe('light');
  });

  it('escribe el atributo que leen los tokens de CSS', () => {
    establecerTema('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');

    establecerTema('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('alterna entre los dos temas', () => {
    expect(alternarTema()).toBe('dark');
    expect(obtenerTema()).toBe('dark');
    expect(alternarTema()).toBe('light');
    expect(obtenerTema()).toBe('light');
  });

  it('recuerda la elección en localStorage, no en sessionStorage', () => {
    establecerTema('dark');
    expect(localStorage.getItem('sire.tema')).toBe('dark');
    expect(sessionStorage.getItem('sire.tema')).toBeNull();
  });

  it('avisa a los suscriptores y deja de hacerlo al darse de baja', () => {
    const oyente = vi.fn();
    const baja = suscribirTema(oyente);

    establecerTema('dark');
    expect(oyente).toHaveBeenCalledWith('dark');

    baja();
    establecerTema('light');
    expect(oyente).toHaveBeenCalledTimes(1);
  });

  it('sigue funcionando si el almacenamiento está bloqueado', () => {
    // Navegación privada o cookies de terceros bloqueadas: setItem lanza.
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('almacenamiento bloqueado');
    });

    expect(() => establecerTema('dark')).not.toThrow();
    expect(obtenerTema()).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});
