"""Cómo le dice un trabajo a la cola si merece la pena reintentarlo."""


class ErrorPermanente(Exception):
    """Reintentar no cambiaría nada: la empresa no existe, falta configuración,
    SUNAT rechazó la clave SOL… El trabajo queda fallido al primer intento."""


class ErrorTransitorio(Exception):
    """El trabajo avanzó pero no terminó (quedan comprobantes con error, SUNAT
    no respondió): vuelve a la cola con espera aunque no sea una excepción de
    red."""
