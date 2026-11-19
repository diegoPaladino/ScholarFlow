"""Renderizacao local de PDFs para o fluxo visual de OCR."""


def abrir_pdf(caminho):
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            'O suporte a PDF requer PyMuPDF. Instale as dependencias de requirements.txt.'
        ) from exc
    documento = pymupdf.open(caminho)
    if documento.needs_pass:
        documento.close()
        raise ValueError('O PDF esta protegido por senha. Salve uma copia sem senha para carregar.')
    if not documento.page_count:
        documento.close()
        raise ValueError('O PDF nao possui paginas.')
    return documento


def contar_paginas_pdf(caminho):
    with abrir_pdf(caminho) as documento:
        return documento.page_count


def renderizar_pagina_pdf(caminho, pagina=0):
    from PIL import Image
    with abrir_pdf(caminho) as documento:
        # 200 dpi preserves small printed grades and scanned document details.
        import pymupdf
        pixmap = documento[pagina].get_pixmap(
            dpi=200, colorspace=pymupdf.csRGB, alpha=False
        )
        return Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
