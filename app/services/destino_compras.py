"""Destino de las compras en el registro («dg», «dng»…), deducido de las ventas.

Vivía dentro de la ruta de exportación; el empaquetado de las solicitudes
necesita la misma regla sin pasar por la ruta (que además llama a SUNAT).
"""

from __future__ import annotations

from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.repositories._mongo import monto_a_float


async def detectar(db, empresa_id: str, periodo: str) -> str | None:
    """«dng» si la empresa solo tiene ventas exoneradas o inafectas; si no, None.

    Si en el periodo o en su histórico reciente solo hay ventas sin base
    imponible, todas sus compras son adquisiciones gravadas destinadas a
    operaciones no gravadas.
    """
    ventas = await repo_comprobantes.listar(db, empresa_id, periodo, libro=Libro.VENTAS, limit=50)
    if not ventas:
        ventas = await repo_comprobantes.listar(db, empresa_id, None, libro=Libro.VENTAS, limit=50)
    if ventas and all(
        monto_a_float(v.get("base_imponible")) == 0 and monto_a_float(v.get("total")) > 0
        for v in ventas
    ):
        return "dng"
    return None
