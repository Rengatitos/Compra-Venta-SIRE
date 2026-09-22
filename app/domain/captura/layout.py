"""Agrupa fragmentos de una misma línea sin repetir la inferencia OCR."""

from app.domain.captura.models import OCRBlock, OCRResult


def lines(ocr: OCRResult) -> OCRResult:
    groups: list[list[OCRBlock]] = []
    for block in ocr.blocks:
        if not block.bbox:
            groups.append([block])
            continue
        top, bottom = min(p[1] for p in block.bbox), max(p[1] for p in block.bbox)
        height = max(bottom - top, 1)
        found = False
        for group in reversed(groups):
            previous = group[-1]
            if previous.page != block.page or not previous.bbox:
                continue
            ptop = min(p[1] for p in previous.bbox)
            pbottom = max(p[1] for p in previous.bbox)
            overlap = min(bottom, pbottom) - max(top, ptop)
            gap = min(p[0] for p in block.bbox) - max(p[0] for p in previous.bbox)
            if overlap > 0.6 * min(height, max(pbottom - ptop, 1)) and 0 <= gap < 12 * height:
                group.append(block)
                found = True
                break
        if not found:
            groups.append([block])
    blocks = []
    for group in groups:
        if len(group) == 1:
            blocks.append(group[0])
            continue
        points = [point for block in group for point in block.bbox]
        left, right = min(p[0] for p in points), max(p[0] for p in points)
        top, bottom = min(p[1] for p in points), max(p[1] for p in points)
        blocks.append(
            OCRBlock(
                text=" ".join(block.text for block in group),
                confidence=min(block.confidence for block in group),
                page=group[0].page,
                bbox=[[left, top], [right, top], [right, bottom], [left, bottom]],
            )
        )
    return ocr.model_copy(update={"blocks": blocks})
