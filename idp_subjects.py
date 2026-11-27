"""Conservative subject candidates, not year/bimester assignments."""
import re
from decimal import Decimal
from idp_fields import normalize_label

CATALOG = ('ARTES', 'CIÊNCIAS', 'CULTURA DE INOVAÇÃO E TECNOLOGIAS',
           'EDUCAÇÃO FÍSICA', 'ENSINO RELIGIOSO', 'GEOGRAFIA', 'HISTÓRIA',
           'LÍNGUA PORTUGUESA', 'MATEMÁTICA')
LABELS = {normalize_label(s): s for s in CATALOG}
LABELS['PORTUGUES'] = 'LÍNGUA PORTUGUESA'


def parse_value(raw):
    if re.fullmatch(r'[0-9]{1,2}(?:[.,][0-9]{1,6})?', raw):
        number = Decimal(raw.replace(',', '.'))
        if 0 <= number <= 10:
            return 'nota', format(number.normalize(), 'f')
    if re.fullmatch(r'[A-Za-z]{1,4}[+-]?', raw):
        return 'conceito', raw.upper()
    return None, None


def extract_subjects(ocr_result):
    if not isinstance(ocr_result, dict) or not isinstance(ocr_result.get('pages'), list):
        raise ValueError('Invalid OCR result')
    candidates, issues, seen = {}, [], set()
    for page in ocr_result['pages']:
        if (not isinstance(page, dict) or type(page.get('page')) is not int
                or page['page'] < 1 or page['page'] in seen
                or not isinstance(page.get('text'), str)):
            raise ValueError('Invalid OCR page')
        seen.add(page['page'])
        for line_no, line in enumerate(page['text'].splitlines(), 1):
            # Match entire known subject label, not a substring or fuzzy guess.
            normalized = normalize_label(line)
            for label in sorted(LABELS, key=len, reverse=True):
                match = re.fullmatch(re.escape(label) + r'(?:\s*:\s*|\s+)(.*)', normalized)
                if not match:
                    continue
                subject = LABELS[label]
                # Preserve original source; normalized value is only a candidate.
                kind, value = parse_value(match.group(1).strip())
                entry = dict(page=page['page'], line=line_no, source=line,
                             kind=kind, value=value, valid=kind is not None)
                candidates.setdefault(subject, []).append(entry)
                break
    subjects = {}
    for subject, entries in candidates.items():
        values = {(e['kind'], e['value']) for e in entries if e['valid']}
        if any(not e['valid'] for e in entries):
            issues.append(dict(disciplina=subject, reason='invalid_or_multiple_values'))
        if len(values) > 1:
            issues.append(dict(disciplina=subject, reason='conflicting_values'))
        if len(values) == 1 and all(e['valid'] for e in entries):
            kind, value = next(iter(values))
            subjects[subject] = dict(kind=kind, value=value)
    return dict(subjects=subjects, candidates=candidates, issues=issues, needs_review=True)
