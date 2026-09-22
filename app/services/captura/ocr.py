import io
from functools import lru_cache

from app.core.captura_config import captura_settings
from app.domain.captura.models import OCRBlock, OCRResult
from app.services.captura.privacy import SensitiveDataMasker


@lru_cache(maxsize=1)
def engine():
    from rapidocr import RapidOCR

    settings = captura_settings()
    if settings.OCR_ENGINE != "rapidocr":
        raise ValueError("Motor OCR no admitido")
    params = {"Rec.lang_type": settings.OCR_LANGUAGE}
    if settings.OCR_MODEL_PATH:
        params["Rec.model_path"] = settings.OCR_MODEL_PATH
    if settings.OCR_KEYS_PATH:
        params["Rec.rec_keys_path"] = settings.OCR_KEYS_PATH
    return RapidOCR(params=params)


def _pages(content: bytes, mime: str):
    import numpy as np
    from PIL import Image, ImageOps

    if mime != "application/pdf":
        with Image.open(io.BytesIO(content)) as image:
            yield np.array(ImageOps.exif_transpose(image).convert("RGB"))[:, :, ::-1]
        return
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(content)
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            width, height = page.get_size()
            scale = min(2, (16_000_000 / max(width * height, 1)) ** 0.5)
            bitmap = page.render(scale=scale)
            try:
                yield np.array(bitmap.to_pil().convert("RGB"))[:, :, ::-1]
            finally:
                bitmap.close()
                page.close()
    finally:
        pdf.close()


def recognize(content: bytes, mime: str) -> OCRResult:
    """Una pasada por página; todos los campos reutilizan los mismos bloques."""
    import cv2

    result = OCRResult()
    detector = cv2.QRCodeDetector()
    for page, image in enumerate(_pages(content, mime), start=1):
        height, width = image.shape[:2]
        if max(height, width) > 3000:
            image = cv2.resize(
                image,
                (int(width * 3000 / max(height, width)), int(height * 3000 / max(height, width))),
            )
        qr, _, _ = detector.detectAndDecode(image)
        if qr:
            result.qr.append(SensitiveDataMasker.cards(qr))
        output = engine()(image)
        if output.txts is None:
            continue
        for text, score, box in zip(output.txts, output.scores, output.boxes, strict=True):
            result.blocks.append(
                OCRBlock(
                    text=SensitiveDataMasker.cards(text),
                    confidence=float(score),
                    bbox=box.tolist(),
                    page=page,
                )
            )
    return result
