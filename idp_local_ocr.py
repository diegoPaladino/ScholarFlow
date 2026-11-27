"""Offline text extraction. Raw text is not a validated school record."""
from io import BytesIO


def _ocr(image):
    import cv2
    import numpy as np
    import pytesseract
    gray = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return pytesseract.image_to_string(binary, lang='por', config='--psm 6', timeout=60)


def extract_text(document, *, force_ocr=False, dpi=300, max_pages=30, ocr=None):
    """Return per-page text and provenance; never invoke an external service."""
    if not isinstance(document, bytes) or not document or len(document) > 50_000_000:
        raise ValueError('Invalid document size or type')
    if type(dpi) is not int or not 100 <= dpi <= 400 or type(max_pages) is not int or not 1 <= max_pages <= 100:
        raise ValueError('Invalid limits')
    from PIL import Image
    recognize = _ocr if ocr is None else ocr
    pages = []
    def add(text, method):
        if not isinstance(text, str):
            raise TypeError('OCR must return text')
        pages.append({'page': len(pages)+1, 'text': text.strip(), 'method': method, 'needs_review': True})
    if document.startswith(b'%PDF-'):
        import fitz
        with fitz.open(stream=document, filetype='pdf') as pdf:
            if pdf.needs_pass or not 1 <= len(pdf) <= max_pages:
                raise ValueError('Encrypted PDF or page limit exceeded')
            for page in pdf:
                text = page.get_text().strip()
                # Conservative heuristic, not a guarantee of text completeness.
                if not force_ocr and sum(c.isalnum() for c in text) >= 20 and not page.get_images():
                    add(text, 'native')
                else:
                    if page.rect.width * page.rect.height * (dpi/72)**2 > 25_000_000:
                        raise ValueError('Raster pixel limit exceeded')
                    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
                    add(recognize(Image.frombytes('RGB', (pix.width, pix.height), pix.samples)), 'ocr')
    elif document.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
        with Image.open(BytesIO(document)) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError('Image pixel limit exceeded')
            add(recognize(image), 'ocr')
    else:
        raise ValueError('Unsupported document format')
    return {'pages': pages, 'text': '\n\n'.join(p['text'] for p in pages), 'needs_review': True}
