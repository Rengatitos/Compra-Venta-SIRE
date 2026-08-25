import io
import json
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT


def _as_text(value):
    if isinstance(value, (dict, list)):
        return str(value)
    return "" if value is None else str(value)


def _normalize_result(value):
    text = _as_text(value).strip().upper()
    return "NO DETERMINADO" if text in {"", "NODETERMINADO"} else text


def _fmt_money(value, fallback: str | None = None) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return fallback if fallback is not None else _as_text(value)


def _consistency_label(invoice_data: dict) -> str:
    detalle = invoice_data.get("detalle") if isinstance(invoice_data.get("detalle"), list) else []
    total = invoice_data.get("TOTAL")
    try:
        total_val = float(total) if total is not None else None
    except (TypeError, ValueError):
        total_val = None

    if not detalle:
        return "Detalle inferido"
    if total_val is None:
        return "Revision recomendada"

    suma = 0.0
    for item in detalle:
        if not isinstance(item, dict):
            continue
        try:
            suma += float(item.get("importe", 0) or 0)
        except (TypeError, ValueError):
            continue

    if abs(suma - total_val) <= 0.01:
        return "Detalle completo"
    if 0 < suma < total_val:
        return "Detalle inferido"
    return "Revision recomendada"

def generate_excel_from_invoice(invoice_data: dict) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Factura"

    ws.append(["Campo", "Valor"])
    header_font = Font(bold=True)
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for key, value in invoice_data.items():
        ws.append([str(key), _as_text(value)])

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 50

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_pdf_from_invoice(invoice_data: dict) -> io.BytesIO:
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor('#333333'), spaceAfter=2)
    subtitle_style = ParagraphStyle('SubtitleStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor('#666666'), spaceAfter=20)
    section_title = ParagraphStyle('SectionTitle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#1976d2'), spaceBefore=15, spaceAfter=8)
    normal_style = styles['Normal']
    italic_style = ParagraphStyle('ItalicStyle', parent=styles['Normal'], fontName='Helvetica-Oblique', textColor=colors.HexColor('#555555'))
    
    elements.append(Paragraph(str(invoice_data.get("_ID_REFERENCIA", "Factura")), title_style))
    elements.append(Paragraph(str(invoice_data.get("NOMBRE_PROVEEDOR", "Proveedor")), subtitle_style))
    
    rd_str = invoice_data.get("RAW_DATA")
    rd = {}
    if rd_str:
        try:
            rd = json.loads(rd_str)
        except Exception:
            pass
            
    tipo_carga = str(rd.get("desTipoCarga") or rd.get("codTipoCarga") or invoice_data.get("tipo_carga") or "-")
    situacion = str(rd.get("desEstadoCP") or rd.get("codSituacion") or invoice_data.get("situacion") or "-")
    moneda = str(rd.get("codMoneda") or rd.get("desMoneda") or invoice_data.get("moneda") or "-")
    estado = str(rd.get("desEstadoComprobante") or invoice_data.get("ESTADO") or "-")
    
    m = rd.get("montos") or {}
    bi_gravada = str(m.get("mtoBIGravadaDG") or m.get("mtoBIGravada") or rd.get("mtoBIGD") or rd.get("mtoBiGravada") or "-")
    igv = str(m.get("mtoIgvIpmDG") or m.get("mtoIGV") or rd.get("mtoIgvGD") or rd.get("mtoIgv") or "-")
    
    total = _fmt_money(invoice_data.get("TOTAL", 0))

    elements.append(Paragraph("INFORMACIÓN GENERAL", section_title))
    data_gen = [
        [Paragraph("<b>Fecha de Emisión:</b>", normal_style), Paragraph(str(invoice_data.get("FECHA_EMISION", "-")), normal_style),
         Paragraph("<b>Monto Total:</b>", normal_style), Paragraph(f"S/ {total}", normal_style)]
    ]
    table_gen = Table(data_gen, colWidths=[110, 150, 100, 150])
    table_gen.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT'), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
    elements.append(table_gen)
    
    elements.append(Paragraph("CLASIFICACIÓN CONTABLE", section_title))
    resultado = str(invoice_data.get("resultado") or "PENDIENTE")
    confianza = str(invoice_data.get("ia_confidence") or "0%")
    observaciones = str(invoice_data.get("Observaciones") or "Sin observaciones detalladas.")
    
    data_clasif = [
        [Paragraph(f"<b>Resultado:</b> {resultado}", normal_style), Paragraph(f"<b>Confianza:</b> {confianza}", normal_style)]
    ]
    table_clasif = Table(data_clasif, colWidths=[200, 300])
    table_clasif.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT'), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
    elements.append(table_clasif)
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"<i>{observaciones}</i>", italic_style))
    
    data_prov = [
        [Paragraph("DATOS DEL PROVEEDOR", section_title), Paragraph("DATOS DEL COMPROBANTE", section_title)],
        [Paragraph(f"<b>RUC:</b> {invoice_data.get('RUC_EMISOR', '-')}", normal_style), Paragraph(f"<b>Tipo de Carga:</b> {tipo_carga}", normal_style)],
        [Paragraph(f"<b>RAZÓN SOCIAL:</b> {invoice_data.get('NOMBRE_PROVEEDOR', '-')}", normal_style), Paragraph(f"<b>Situación:</b> {situacion}", normal_style)],
        ["", Paragraph(f"<b>Moneda:</b> {moneda}", normal_style)],
        ["", Paragraph(f"<b>Estado:</b> {estado}", normal_style)]
    ]
    table_prov = Table(data_prov, colWidths=[260, 260])
    table_prov.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT'), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
    elements.append(table_prov)
    
    elements.append(Paragraph("MONTOS", section_title))
    data_montos = [
        [Paragraph(f"<b>BI Gravada:</b> {bi_gravada}", normal_style),
         Paragraph(f"<b>IGV:</b> {igv}", normal_style),
         Paragraph(f"<b>Total:</b> S/ {total}", normal_style)]
    ]
    table_montos = Table(data_montos, colWidths=[173, 173, 173])
    table_montos.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT'), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
    elements.append(table_montos)
    
    elements.append(Paragraph("RESUMEN DE COMPRAS", section_title))
    detalle = invoice_data.get("detalle")
    
    if detalle and isinstance(detalle, list) and len(detalle) > 0:
        for idx, item in enumerate(detalle):
            prod = str(item.get("producto", "Item general / No especificado"))
            cat = str(item.get("categoria_contable", "-"))
            cant = str(item.get("cantidad", "N/A"))
            imp = _fmt_money(item.get("importe", 0), fallback=str(item.get("importe", "0.00")))
            razon = str(item.get("razon", ""))
            
            p1 = Paragraph(f"<b>{prod}</b>", normal_style)
            p2 = Paragraph(f"{cat} — Cant: {cant} — Importe: S/ {imp}", normal_style)
            p3 = Paragraph(f"<i>{razon}</i>", italic_style) if razon else ""
            
            item_data = [[p1], [p2]]
            if p3: item_data.append([p3])
            
            t_item = Table(item_data, colWidths=[520])
            t_item.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOTTOMPADDING', (0,-1), (-1,-1), 8),
            ]))
            elements.append(t_item)
            
            if idx < len(detalle) - 1:
                elements.append(Spacer(1, 4))
                
    else:
        elements.append(Paragraph("No hay detalle de la compra analizado.", normal_style))
    
    doc.build(elements)
    output.seek(0)
    return output


def generate_excel_from_invoices_batch(invoices_data: list[dict]) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Facturas"

    headers = [
        "ID_REFERENCIA",
        "RUC_EMISOR",
        "NOMBRE_PROVEEDOR",
        "FECHA_EMISION",
        "TOTAL",
        "RESULTADO",
        "CONSISTENCIA",
        "ESTADO",
    ]
    ws.append(headers)

    header_font = Font(bold=True)
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for inv in invoices_data:
        ws.append([
            _as_text(inv.get("_ID_REFERENCIA")),
            _as_text(inv.get("RUC_EMISOR")),
            _as_text(inv.get("NOMBRE_PROVEEDOR")),
            _as_text(inv.get("FECHA_EMISION")),
            _as_text(inv.get("TOTAL")),
            _normalize_result(inv.get("resultado")),
            _consistency_label(inv),
            _as_text(inv.get("ESTADO")),
        ])

    widths = {
        "A": 22,
        "B": 16,
        "C": 38,
        "D": 16,
        "E": 14,
        "F": 18,
        "G": 22,
        "H": 18,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_pdf_from_invoices_batch(invoices_data: list[dict]) -> io.BytesIO:
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#1e293b"))
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#475569"), spaceAfter=20)
    
    item_title = ParagraphStyle("ItemTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor("#0f172a"), spaceBefore=12, spaceAfter=2)
    item_body = ParagraphStyle("ItemBody", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=14, spaceAfter=2)
    item_obs = ParagraphStyle("ItemObs", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=9, leading=12, textColor=colors.HexColor("#334155"), spaceAfter=8)

    elements.append(Paragraph("Reporte Detallado de Facturas", title_style))
    
    total_count = len(invoices_data)
    total_amount = 0.0
    for inv in invoices_data:
        try:
            total_amount += float(inv.get("TOTAL") or 0)
        except (TypeError, ValueError):
            continue
            
    resumen = f"Total comprobantes: {total_count} &nbsp;&nbsp;|&nbsp;&nbsp; Monto Acumulado: S/ {total_amount:,.2f}"
    elements.append(Paragraph(resumen, subtitle_style))
    
    for inv in invoices_data[:500]:
        ref = _as_text(inv.get("_ID_REFERENCIA"))
        prov = _as_text(inv.get("NOMBRE_PROVEEDOR", "Proveedor Desconocido"))
        monto = _fmt_money(inv.get("TOTAL"))

        res = _normalize_result(inv.get("resultado"))
        conf = _as_text(inv.get("ia_confidence")) or "0%"
        obs = _as_text(inv.get("Observaciones")) or "Sin observaciones detalladas registradas."
        
        elements.append(Paragraph(f"<b>{ref}</b> — {prov}", item_title))
        
        body_text = f"<b>Monto Total:</b> S/ {monto} &nbsp;&nbsp;|&nbsp;&nbsp; "
        body_text += f"<b>Resultado:</b> {res} &nbsp;&nbsp;|&nbsp;&nbsp; "
        body_text += f"<b>Confianza IA:</b> {conf}"
        elements.append(Paragraph(body_text, item_body))
        
        elements.append(Paragraph(f"<i>Justificación: {obs}</i>", item_obs))
        
        sep_table = Table([['']], colWidths=['100%'])
        sep_table.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8)
        ]))
        elements.append(sep_table)

    doc.build(elements)
    output.seek(0)
    return output
