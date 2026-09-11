import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

from app.domain.comprobante import Libro
from app.repositories.comprobantes import listar_anulados_sunat


def test_anulados_usa_descripcion_original_y_todo_el_registro():
    db = MagicMock()
    cursor = db.__getitem__.return_value.find.return_value
    cursor.to_list = AsyncMock(return_value=[])
    asyncio.run(listar_anulados_sunat(db, "empresa", "202608", Libro.VENTAS))
    filtro = db.__getitem__.return_value.find.call_args.args[0]
    assert filtro['empresa_id'] == 'empresa'
    assert filtro['periodo'] == '202608'
    assert filtro['libro'] == 'ventas'
    assert filtro['origen'] == 'sire'
    assert 'glosa' not in filtro
    patron = filtro['detalle_sunat.descripcion']['$regex']
    assert re.search(patron, 'Comprobante Anulado', re.I)
    assert re.search(patron, 'ANULADOS', re.I)
    assert not re.search(patron, 'reanulado', re.I)
    cursor.to_list.assert_awaited_once_with(length=None)
