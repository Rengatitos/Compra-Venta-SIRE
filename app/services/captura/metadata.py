import io
import re
from datetime import datetime


def _date(text: str | None) -> str | None:
    if not text:
        return None
    match = re.match(r"(?:D:)?(\d{4})[:/-]?(\d{2})[:/-]?(\d{2})", str(text))
    try:
        return datetime(*map(int, match.groups())).date().isoformat() if match else None
    except ValueError:
        return None


def extract_file_metadata(content: bytes, mime: str) -> dict:
    result = {
        "original_date": None,
        "creation_date": None,
        "modification_date": None,
        "source": None,
        "confidence": 0,
    }
    if mime == "application/pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(content)
        try:
            metadata = pdf.get_metadata_dict()
            result.update(
                creation_date=_date(metadata.get("CreationDate")),
                modification_date=_date(metadata.get("ModDate")),
                source="PDF",
            )
        finally:
            pdf.close()
    else:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            exif = image.getexif()
            nested = exif.get_ifd(34665) if 34665 in exif else {}
            result.update(
                original_date=_date(nested.get(36867) or exif.get(36867)),
                creation_date=_date(nested.get(36868) or exif.get(36868)),
                modification_date=_date(exif.get(306)),
                source="EXIF",
            )
    if any(result[key] for key in ("original_date", "creation_date", "modification_date")):
        result["confidence"] = 0.5
    return result
