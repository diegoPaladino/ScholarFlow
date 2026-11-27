"""Review-only bridge to the original report-card validator."""
from copy import deepcopy
from decimal import Decimal
from boletim_bimestral import validar


def validate_review(review, *, matricula, nome_esperado, year):
    if review.get('needs_review') is not True or review.get('ready_for_submission') is not False:
        raise ValueError('Expected review-only payload')
    payload = deepcopy(review['payload'])
    if type(year) is not int or not 1900 <= year <= 2099 or payload['ano'] != str(year):
        raise ValueError('Document year mismatch')
    if not isinstance(nome_esperado, str) or not nome_esperado.strip():
        raise ValueError('Expected student name required')
    validated = validar(payload, matricula, nome_esperado, ano_selecionado=str(year))
    def grades(items):
        return sorted((x['disciplina'], x['bimestre'], Decimal(x['nota'])) for x in items)
    if grades(payload['notas']) != grades(validated['notas']):
        raise ValueError('Legacy validator changed grade records')
    return dict(payload=validated, evidence=deepcopy(review['evidence']), issues=deepcopy(review['issues']), needs_review=True, ready_for_submission=False)
