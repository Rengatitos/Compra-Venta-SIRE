"""Los vouchers de Apaclla Bot de un periodo y su asociación a un comprobante."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import empresa_id, periodo_valido
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.repositories import periodos as repo_periodos
from app.schemas.voucher import AsociacionVoucher, PagoVoucher, VoucherPeriodo
from app.services import integracion_externos, pagos_vouchers

router = APIRouter()


async def _asegurar_periodo(db, empresa: str, periodo: str) -> None:
    if not await repo_periodos.obtener(db, empresa, periodo):
        raise HTTPException(status_code=404, detail="Periodo no encontrado para esta empresa")


@router.get("", response_model=list[VoucherPeriodo], summary="Vouchers del periodo")
async def listar_vouchers(
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    libro: Libro | None = Query(None),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)
    await integracion_externos.refrescar(db, empresa, periodo)
    return await pagos_vouchers.vouchers_con_candidatas(
        db, empresa, periodo, libro.value if libro else None
    )


@router.put(
    "/{voucher_id}/asociacion",
    response_model=PagoVoucher,
    summary="Asociar un voucher al comprobante que paga, o desasociarlo",
)
async def asociar_voucher(
    voucher_id: str,
    datos: AsociacionVoucher,
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)
    try:
        return await pagos_vouchers.asociar_manual(
            db, empresa, periodo, voucher_id, datos.serie_numero, datos.periodo
        )
    except pagos_vouchers.VoucherNoEncontrado as exc:
        raise HTTPException(status_code=404, detail="Voucher no encontrado en el periodo") from exc
    except pagos_vouchers.ComprobanteNoEncontrado as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No hay un comprobante {datos.serie_numero} en el libro del voucher, "
                "ni en su periodo ni en el anterior"
            ),
        ) from exc
