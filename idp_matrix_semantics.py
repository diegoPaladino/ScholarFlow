"""Explicit, human-reviewed column mapping; never infer periods or recovery grades."""
from idp_fields import normalize_label
from idp_subjects import LABELS, parse_value


def interpret(matrix, *, year, subject_column, periods, first_row, last_row):
    cells = matrix['cells']
    if type(year) is not int or not 1900 <= year <= 2099:
        raise ValueError('Invalid year')
    if not cells or not cells[0] or any(len(row)!=len(cells[0]) for row in cells):
        raise ValueError('Invalid matrix')
    width=len(cells[0])
    if type(subject_column) is not int or not 0<=subject_column<width:
        raise ValueError('Invalid subject column')
    if not isinstance(periods,dict) or not periods or any(type(c) is not int or not 0<=c<width or c==subject_column or type(p) is not int or not 1<=p<=4 for c,p in periods.items()) or len(set(periods.values()))!=len(periods):
        raise ValueError('Invalid period mapping')
    if type(first_row) is not int or type(last_row) is not int or not 0<=first_row<last_row<=len(cells):
        raise ValueError('Invalid row range')
    candidates,issues,groups=[],[],{}
    for r in range(first_row,last_row):
        label=normalize_label(cells[r][subject_column]['text'] or '')
        subject=LABELS.get(label) or ('ARTES' if label=='ARTE' else None)
        if subject is None:
            issues.append({'row':r,'reason':'unknown_subject'})
            continue
        for c,p in periods.items():
            raw=cells[r][c]['text']
            kind,value=parse_value(raw.strip()) if isinstance(raw,str) else (None,None)
            entry=dict(ano=year,bimestre=p,disciplina=subject,kind=kind,value=value,row=r,column=c)
            candidates.append(entry)
            groups.setdefault((subject,p),[]).append(entry)
    records=[]
    for entries in groups.values():
        e=entries[0]
        if len(entries)!=1 or e['kind']!='nota':
            issues.append(dict(row=e['row'],column=e['column'],reason='duplicate_subject_period' if len(entries)!=1 else 'missing_or_invalid_grade'))
        else:
            records.append({k:e[k] for k in ('ano','bimestre','disciplina','kind','value')})
    return dict(records=records,candidates=candidates,issues=issues,needs_review=True)
