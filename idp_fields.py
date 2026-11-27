"""Conservative labelled-field candidates; never a validated school record."""
import re
import unicodedata
from datetime import date

LABELS = {
    'ALUNO': 'nome_aluno', 'NOME DO ALUNO': 'nome_aluno', 'NOME DA ALUNA': 'nome_aluno',
    'MATRICULA': 'numero_matricula', 'NUMERO DE MATRICULA': 'numero_matricula',
    'ANO LETIVO': 'ano', 'ESCOLA': 'nome_escola', 'NOME DA ESCOLA': 'nome_escola',
    'CIDADE': 'cidade', 'UF': 'uf', 'SERIE': 'serie', 'TURMA': 'turma',
    'CARGA HORARIA': 'carga_horaria', 'DATA DE NASCIMENTO': 'data_nascimento',
}
UFS = set('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())

def normalize_label(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', text.upper()) if not unicodedata.combining(c)).split())

def valid(field, value):
    if field == 'numero_matricula': return bool(re.fullmatch(r'[0-9]+', value))
    if field == 'ano': return bool(re.fullmatch(r'(?:19|20)[0-9]{2}', value))
    if field == 'uf': return value in UFS
    if field == 'data_nascimento':
        try:
            if not re.fullmatch(r'[0-9]{2}/[0-9]{2}/[0-9]{4}', value): return False
            d,m,y = map(int,value.split('/')); date(y,m,d); return True
        except ValueError: return False
    if field in ('nome_aluno','nome_escola','cidade'): return any(c.isalpha() for c in value)
    return bool(value)

def extract_fields(ocr_result):
    """Accept extract_text output; only explicit colon-labelled lines are candidates."""
    if not isinstance(ocr_result, dict) or not isinstance(ocr_result.get('pages'), list):
        raise ValueError('Invalid OCR result')
    candidates = {}; issues = []; seen = set()
    for page in ocr_result['pages']:
        if not isinstance(page, dict) or type(page.get('page')) is not int or page['page'] < 1 or page['page'] in seen or not isinstance(page.get('text'), str):
            raise ValueError('Invalid OCR page')
        seen.add(page['page'])
        for number, line in enumerate(page['text'].splitlines(), 1):
            label, sep, raw = line.partition(':')
            field = LABELS.get(normalize_label(label)) if sep else None
            if field is None: continue
            value = raw.strip()
            if field == 'uf': value = value.upper()
            evidence = {'value': value, 'page': page['page'], 'line': number, 'source': line, 'valid': valid(field,value)}
            candidates.setdefault(field, []).append(evidence)
    fields = {}
    for field, entries in candidates.items():
        values = {e['value'] for e in entries if e['valid']}
        if any(not e['valid'] for e in entries): issues.append({'field':field,'reason':'invalid_value'})
        if len(values)>1: issues.append({'field':field,'reason':'conflicting_values'})
        if len(values)==1 and all(e['valid'] for e in entries): fields[field] = next(iter(values))
    return {'fields':fields,'candidates':candidates,'issues':issues,'needs_review':True}
