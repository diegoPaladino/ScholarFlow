"""Offline review payload; never authorizes GEMUL writes."""
from copy import deepcopy
from math import isfinite
from idp_subjects import CATALOG


def adapt_boletim(merged, *, year, numero_matricula, nome_aluno, turma):
    if type(year) is not int or not 1900 <= year <= 2099:
        raise ValueError('Invalid year')
    if merged.get('needs_review') is not True:
        raise ValueError('Expected review-required input')
    if any(not isinstance(v, str) for v in (numero_matricula, nome_aluno, turma)):
        raise ValueError('Invalid metadata')
    notas, seen = [], set()
    for r in merged['records']:
        if type(r['ano']) is not int or r['ano'] != year:
            raise ValueError('Document year mismatch')
        p, s, v = r['bimestre'], r['disciplina'], r['value']
        if type(p) is not int or not 1 <= p <= 4 or s not in CATALOG or r['kind'] != 'nota' or type(v) not in (int, float) or not isfinite(v) or not 0 <= v <= 10:
            raise ValueError('Invalid grade record')
        if (s,p) in seen:
            raise ValueError('Duplicate grade')
        seen.add((s,p))
        notas.append(dict(disciplina=s,bimestre=str(p),nota=str(v)))
    return dict(payload=dict(numero_matricula=numero_matricula,nome_aluno=nome_aluno,ano=str(year),turma=turma,notas=notas), evidence=deepcopy(merged['records']), issues=deepcopy(merged['issues']), needs_review=True, ready_for_submission=False)
