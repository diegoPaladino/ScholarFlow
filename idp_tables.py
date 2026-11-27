"""Conservative explicit delimited tables; all results require human review."""
import re
from idp_fields import normalize_label
from idp_subjects import LABELS, parse_value


def extract_tables(ocr_result):
    if not isinstance(ocr_result, dict) or not isinstance(ocr_result.get('pages'), list):
        raise ValueError('Invalid OCR result')
    candidates, issues, seen = {}, [], set()
    for page in ocr_result['pages']:
        if (not isinstance(page, dict) or type(page.get('page')) is not int
                or page['page'] < 1 or page['page'] in seen
                or not isinstance(page.get('text'), str)):
            raise ValueError('Invalid OCR page')
        seen.add(page['page'])
        year, columns = None, None
        for number, line in enumerate(page['text'].splitlines(), 1):
            norm = normalize_label(line)
            if norm.startswith('ANO LETIVO:'):
                raw = norm.partition(':')[2].strip()
                year = int(raw) if re.fullmatch(r'(?:19|20)[0-9]{2}', raw) else None
                columns = None
                continue
            cells = [normalize_label(c) for c in line.split('|')]
            if cells[0] == 'DISCIPLINA':
                columns = None
                parsed = []
                for cell in cells[1:]:
                    match = re.fullmatch(r'([1-4])(?:[º°O])? BIMESTRE', cell)
                    if not match: break
                    parsed.append(int(match.group(1)))
                if year is not None and parsed and len(parsed) == len(cells)-1 and len(set(parsed)) == len(parsed):
                    columns = parsed
                else:
                    issues.append(dict(page=page['page'], line=number, reason='invalid_header'))
                continue
            if columns is None: continue
            subject = LABELS.get(cells[0])
            if subject is None or len(cells) != len(columns)+1:
                issues.append(dict(page=page['page'], line=number, reason='unrecognized_row'))
                columns = None
                continue
            for period, raw in zip(columns, cells[1:]):
                kind, value = parse_value(raw)
                key = (year, period, subject)
                candidates.setdefault(key, []).append(dict(ano=year,bimestre=period,disciplina=subject,kind=kind,value=value,page=page['page'],line=number,source=line))
    records = []
    for key, entries in candidates.items():
        values = {(e['kind'],e['value']) for e in entries}
        if len(values) == 1 and entries[0]['kind'] is not None:
            records.append({k:entries[0][k] for k in ('ano','bimestre','disciplina','kind','value')})
        else:
            issues.append(dict(ano=key[0],bimestre=key[1],disciplina=key[2],reason='invalid_or_conflicting_cell'))
    return dict(records=records,candidates=[e for entries in candidates.values() for e in entries],issues=issues,needs_review=True)
