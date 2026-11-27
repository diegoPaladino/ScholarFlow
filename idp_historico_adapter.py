"""Explicit annual records only; offline review payload."""
from copy import deepcopy
import re

NOTES = ('nota_arte','nota_ciencias','nota_cultura','nota_educacao_fisica','nota_ensino_religioso','nota_geografia','nota_historia','nota_lingua_portuguesa','nota_matematica')
FIELDS = ('ano','serie','nome_escola','cidade','uf','carga_horaria','txt_observacoes','txt_observacoes_gerais','cursando') + NOTES


def adapt_historico(records, *, numero_matricula, nome_aluno, issues=()):
    if not all(isinstance(x,str) for x in (numero_matricula,nome_aluno)) or not nome_aluno.strip():
        raise ValueError('Invalid identity')
    if not isinstance(records,list) or not records:
        raise ValueError('Annual records required')
    annual, seen = [], set()
    for record in records:
        if not isinstance(record,dict) or record.get('period_type') != 'annual' or set(record)-set(FIELDS)-{'period_type','disciplinas_extra','sources'}:
            raise ValueError('Explicit annual record required')
        row = {k:record.get(k,'') for k in FIELDS}
        if not all(isinstance(v,str) for v in row.values()) or not re.fullmatch(r'(19|20)[0-9]{2}',row['ano']) or not row['serie'].strip():
            raise ValueError('Invalid annual fields')
        if row['ano'] in seen:
            raise ValueError('Duplicate year')
        seen.add(row['ano'])
        extras = record.get('disciplinas_extra',[])
        if not isinstance(extras,list) or any(not isinstance(e,dict) or set(e)!={'disciplina','nota'} or not all(isinstance(v,str) for v in e.values()) or not e['disciplina'].strip() for e in extras):
            raise ValueError('Invalid extra subjects')
        row['disciplinas_extra'] = deepcopy(extras)
        annual.append(row)
    annual.sort(key=lambda r:r['ano'])
    # Avoid creating a second, inferred annual record through the legacy fallback.
    payload = {k:'' for k in FIELDS if k!='cursando'}
    payload.update(numero_matricula=numero_matricula,nome_aluno=nome_aluno,disciplinas_extra=[],historicos=annual)
    return dict(payload=payload,evidence=deepcopy(records),issues=deepcopy(list(issues)),needs_review=True,ready_for_submission=False)
