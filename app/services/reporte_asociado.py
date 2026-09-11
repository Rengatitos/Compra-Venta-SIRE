"""Libro conjunto y control de numeración por registro, emisor, tipo y serie."""
import io
import re
import tempfile
import zipfile
from collections import defaultdict, Counter
from copy import copy
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Font

from app.domain.comprobante import Libro
from app.services import almacen_pdf
from app.repositories import comprobantes
from app.services.comprobante_service import serializar_lote
from app.services.glosa import obtener_glosa
from app.services.plantilla_excel import excel_plantilla
from app.services.revision_comprobantes import anulado

MESES = ('ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO SEPTIEMBRE OCTUBRE NOVIEMBRE DICIEMBRE').split()


def nombre(usuario, periodo):
    return f"{re.sub(r'[^A-Za-z0-9_-]', '', usuario)}-{MESES[int(periodo[4:6])-1]}{periodo[:4]}"


async def registros(db, empresa, periodo):
    salida = {}
    for libro in (Libro.VENTAS, Libro.COMPRAS):
        filas = []
        while True:
            pagina = await comprobantes.listar(db, str(empresa['_id']), periodo, libro=libro, skip=len(filas), limit=500)
            filas.extend(pagina)
            if len(pagina) < 500:
                break
        salida[libro] = filas
    return salida


def estado(registros):
    filas = [f for grupo in registros.values() for f in grupo]
    pendientes = sum(not bool(obtener_glosa(f)) for f in filas)
    libros_completos = all(registros.get(libro) for libro in (Libro.COMPRAS, Libro.VENTAS))
    return {'habilitado': libros_completos and pendientes == 0, 'pendientes': pendientes}


def excel(registros, periodo, ruc):
    wb = Workbook()
    control = wb.active
    control.title = 'Correlatividad cp'
    control.append(['CONTROL DE NUMERACIÓN DE COMPROBANTES · RVIE Y RCE'])
    control.append(['Los saltos corresponden solo a los documentos del periodo; no prueban omisiones del emisor.'])
    control.append(['Mes', 'Registro', 'Emisor / Proveedor', 'Tipo', 'Serie', 'Del', 'Al', 'Cantidad', 'Saltos', 'Duplicados', 'Fuera de secuencia por fecha'])
    for libro, filas in registros.items():
        grupos = defaultdict(list)
        for f in filas:
            emisor = ruc if libro == Libro.VENTAS else f.get('documento_contraparte', '')
            grupos[(emisor, f.get('tipo_cp', ''), f.get('serie', ''))].append(f)
        for (emisor, tipo, serie), grupo in sorted(grupos.items(), key=lambda par: str(par[0])):
            numeros = [int(str(f.get('numero'))) for f in grupo if str(f.get('numero', '')).isdigit()]
            orden = sorted(set(numeros))
            saltos = [str(a+1) if b == a+2 else f'{a+1}-{b-1}' for a, b in zip(orden, orden[1:]) if b > a+1]
            duplicados = [str(n) for n, cantidad in Counter(numeros).items() if cantidad > 1]
            por_fecha = sorted(grupo, key=lambda f: (str(f.get('fecha_emision') or ''), int(str(f.get('numero'))) if str(f.get('numero', '')).isdigit() else -1))
            secuencia = [int(str(f['numero'])) for f in por_fecha if str(f.get('numero', '')).isdigit()]
            control.append([MESES[int(periodo[4:6])-1], libro.value, emisor, tipo, serie,
                min(orden) if orden else None, max(orden) if orden else None, len(grupo),
                ', '.join(saltos) or ('Numeración no numérica' if len(numeros) != len(grupo) else ''),
                ', '.join(duplicados), 'Revisar' if any(b < a for a, b in zip(secuencia, secuencia[1:])) else ''])
    control.freeze_panes = 'A4'
    control.auto_filter.ref = f'A3:K{max(3, control.max_row)}'
    for celda in control[3]:
        celda.font = Font(bold=True)
    for col in 'ABCDEFGHIJK':
        control.column_dimensions[col].width = 24
    for libro in (Libro.VENTAS, Libro.COMPRAS):
        filas = [fila for fila in registros[libro] if not anulado(fila)]
        original = load_workbook(excel_plantilla(serializar_lote(filas), libro)).worksheets[0]
        hoja = wb.create_sheet('Registro de ventas' if libro == Libro.VENTAS else 'Registro de compras')
        for rango in original.merged_cells.ranges:
            hoja.merge_cells(str(rango))
        for fila in original:
            for celda in fila:
                if isinstance(celda, MergedCell):
                    continue
                destino = hoja.cell(celda.row, celda.column, celda.value)
                destino.font = copy(celda.font)
                destino.fill = copy(celda.fill)
                destino.border = copy(celda.border)
                destino.alignment = copy(celda.alignment)
                destino.number_format = celda.number_format
                destino.protection = copy(celda.protection)
        for clave, dimension in original.column_dimensions.items():
            destino = hoja.column_dimensions[clave]
            destino.width = dimension.width
            destino.hidden = dimension.hidden
            destino.bestFit = dimension.bestFit
            destino.outlineLevel = dimension.outlineLevel
            destino.collapsed = dimension.collapsed
        for clave, dimension in original.row_dimensions.items():
            destino = hoja.row_dimensions[clave]
            destino.height = dimension.height
            destino.hidden = dimension.hidden
            destino.outlineLevel = dimension.outlineLevel
            destino.collapsed = dimension.collapsed
        hoja.freeze_panes = original.freeze_panes
    for fila in control:
        for celda in fila:
            if isinstance(celda.value, str):
                celda.data_type = 's'
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def zip_reporte(registros, periodo, ruc, usuario):
    """Crea el ZIP con el libro conjunto y los PDFs de ambos registros."""
    ruta_temporal = tempfile.NamedTemporaryFile(suffix='.zip', delete=False).name
    try:
        with zipfile.ZipFile(ruta_temporal, 'w', zipfile.ZIP_DEFLATED) as archivo:
            archivo.writestr(f'{nombre(usuario, periodo)}.xlsx', excel(registros, periodo, ruc))
            for carpeta in ('comprobantes compra', 'comprobantes venta'):
                archivo.writestr(f'{carpeta}/', '')
            for libro, carpeta in (
                (Libro.COMPRAS, 'comprobantes compra'),
                (Libro.VENTAS, 'comprobantes venta'),
            ):
                base = almacen_pdf.raiz_periodo(ruc, libro, periodo)
                for pdf in almacen_pdf.listar(ruc, libro, periodo):
                    archivo.write(pdf, arcname=f'{carpeta}/{pdf.relative_to(base).as_posix()}')
    except Exception:
        Path(ruta_temporal).unlink(missing_ok=True)
        raise
    return ruta_temporal
