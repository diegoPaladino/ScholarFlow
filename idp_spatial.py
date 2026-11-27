"""Local word geometry; coordinates normalized to the displayed page, not deskewed."""
import math
from io import BytesIO

def _word(text, box, width, height, confidence=None):
    if not isinstance(text,str) or not text.strip(): return None
    x0,y0,x1,y1=map(float,box)
    if not all(map(math.isfinite,(x0,y0,x1,y1))) or not (0<=x0<x1<=width and 0<=y0<y1<=height): return None
    return {'text':text.strip(),'bbox':[x0/width,y0/height,x1/width,y1/height],'confidence':confidence}

def _ocr(image):
    import pytesseract
    return pytesseract.image_to_data(image,lang='por',config='--psm 6',output_type=pytesseract.Output.DICT,timeout=60)

def _image_words(image, recognize):
    if image.width*image.height>25_000_000: raise ValueError('Pixel limit exceeded')
    data=recognize(image.convert('RGB'))
    keys=('text','left','top','width','height','conf')
    if len({len(data[k]) for k in keys})!=1: raise ValueError('Invalid OCR columns')
    words=[]
    for text,x,y,w,h,c in zip(*(data[k] for k in keys)):
        c=float(c)
        if not math.isfinite(c) or not 0<=c<=100: continue
        x,y,w,h=map(float,(x,y,w,h))
        word=_word(text,(x,y,x+w,y+h),image.width,image.height,c/100)
        if word: words.append(word)
    return words

def extract_spatial(document, *, dpi=300, max_pages=30, force_ocr=False, ocr=None):
    if not isinstance(document,bytes) or not 0<len(document)<=50_000_000: raise ValueError('Invalid document')
    if type(dpi) is not int or not 100<=dpi<=400 or type(max_pages) is not int or not 1<=max_pages<=100: raise ValueError('Invalid limits')
    from PIL import Image, ImageOps
    recognize=_ocr if ocr is None else ocr
    pages=[]
    def add(words,method): pages.append({'page':len(pages)+1,'method':method,'words':words,'needs_review':True})
    if document.startswith(b'%PDF-'):
        import fitz
        with fitz.open(stream=document,filetype='pdf') as pdf:
            if pdf.needs_pass or not 1<=len(pdf)<=max_pages: raise ValueError('PDF unavailable or page limit exceeded')
            for page in pdf:
                native=page.get_text('words')
                if not force_ocr and sum(sum(c.isalnum() for c in w[4]) for w in native)>=20 and not page.get_images():
                    words=[]
                    for w in native:
                        r=fitz.Rect(w[:4])*page.rotation_matrix
                        item=_word(w[4],r,page.rect.width,page.rect.height)
                        if item: words.append(item)
                    add(words,'native')
                else:
                    if page.rect.width*page.rect.height*(dpi/72)**2>25_000_000: raise ValueError('Pixel limit exceeded')
                    pix=page.get_pixmap(dpi=dpi,colorspace=fitz.csRGB,alpha=False)
                    add(_image_words(Image.frombytes('RGB',(pix.width,pix.height),pix.samples),recognize),'ocr')
    elif document.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff')):
        with Image.open(BytesIO(document)) as image:
            if image.width*image.height>25_000_000: raise ValueError('Pixel limit exceeded')
            add(_image_words(ImageOps.exif_transpose(image),recognize),'ocr')
    else: raise ValueError('Unsupported format')
    return {'pages':pages,'needs_review':True,'coordinate_space':'normalized_display_page'}
