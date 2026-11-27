"""Conservative consolidation of explicitly mapped matrices for one document."""
from collections import defaultdict
from math import isfinite


def merge_matrices(matrices):
    groups = defaultdict(list)
    issues = []
    for index, matrix in enumerate(matrices):
        if matrix.get('needs_review') is not True:
            raise ValueError('Expected review-required matrix')
        for issue in matrix['issues']:
            issues.append({'matrix': index, 'detail': dict(issue)})
        # Include rejected candidates so a valid value elsewhere cannot hide ambiguity.
        for entry in matrix['candidates']:
            year, period, subject = (entry[k] for k in ('ano', 'bimestre', 'disciplina'))
            if type(year) is not int or not 1900 <= year <= 2099 or type(period) is not int or not 1 <= period <= 4 or not isinstance(subject, str) or not subject.strip():
                raise ValueError('Invalid record identity')
            groups[year, period, subject].append((index, entry))
    records = []
    for (year, period, subject), entries in sorted(groups.items()):
        values = [e['value'] for _, e in entries]
        valid = all(e['kind'] == 'nota' and type(v) in (int, float) and isfinite(v) and 0 <= v <= 10 for (_, e), v in zip(entries, values))
        sources = [{'matrix': i, 'row': e['row'], 'column': e['column']} for i, e in entries]
        key = dict(ano=year, bimestre=period, disciplina=subject)
        if not valid or len(entries) != 1:
            issues.append(dict(key, reason='ambiguous_or_invalid_grade', sources=sources))
        else:
            records.append(dict(key, kind='nota', value=values[0], sources=sources))
    return dict(records=records, issues=issues, needs_review=True)
