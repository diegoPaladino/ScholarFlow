"""Explicitly authorized bridge from benchmark bytes to existing OpenAI extractors."""
from pathlib import Path
from tempfile import TemporaryDirectory


NAMES = {'historico': 'extrair_campos_historico_com_openai',
         'boletim': 'extrair_campos_boletim_com_openai',
         'documento_civil': 'extrair_campos_documento_civil_com_openai'}


def suffix(document):
    if document.startswith(b'%PDF-'):
        return '.pdf'
    if document.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if document.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    raise ValueError('Unsupported benchmark document format')


def make_extractor(engine, *, model, allow_external=False):
    """Engine is an explicitly supplied module/object; never import GUI here."""
    if allow_external is not True:
        raise PermissionError('External document processing requires explicit authorization')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('Explicit model required')
    methods = {kind: getattr(engine, name) for kind, name in NAMES.items()}
    if not all(callable(fn) for fn in methods.values()):
        raise TypeError('Invalid extraction engine')

    def extract(kind, document):
        if kind not in methods or not isinstance(document, bytes):
            raise ValueError('Invalid benchmark input')
        ext = suffix(document)
        with TemporaryDirectory(prefix='idp_benchmark_') as folder:
            path = Path(folder) / ('document' + ext)
            path.write_bytes(document)
            return methods[kind]([str(path)], model=model)
    return extract
