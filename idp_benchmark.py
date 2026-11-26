"""Offline exact-match evaluator for verified extraction JSON (no I/O)."""
import math


def _flatten(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('JSON keys must be strings')
            yield from _flatten(item, path + (key,))
    elif isinstance(value, list):
        # Match semantic rows, not their position in the extraction.
        identities = {'notas': ('disciplina', 'bimestre'),
                      'historicos': ('ano', 'serie'),
                      'disciplinas_extra': ('disciplina',)}
        keys = identities.get(path[-1] if path else None)
        if keys is None:
            raise ValueError('Unsupported array')
        seen = set()
        for row in value:
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in keys):
                raise ValueError('Invalid row identity')
            identity = tuple(row[k] for k in keys)
            if identity in seen:
                raise ValueError('Duplicate row identity')
            seen.add(identity)
            yield from _flatten({k: v for k, v in row.items() if k not in keys}, path + (identity,))
    elif value is None or type(value) in (str, int, float, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Nonfinite number')
        yield path, value
    else:
        raise ValueError('Unsupported JSON value')


def evaluate(expected, actual):
    """Return counts only; no student values or field paths are returned."""
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        raise ValueError('Expected JSON objects')
    ref, pred = dict(_flatten(expected)), dict(_flatten(actual))
    common = ref.keys() & pred.keys()
    correct = sum(type(ref[k]) is type(pred[k]) and ref[k] == pred[k] for k in common)
    wrong = len(common) - correct
    missing = len(ref.keys() - pred.keys())
    extra = len(pred.keys() - ref.keys())
    union = correct + wrong + missing + extra
    return dict(correct=correct, wrong=wrong, missing=missing, extra=extra,
                expected_fields=len(ref), predicted_fields=len(pred),
                accuracy=correct / len(ref) if ref else None,
                precision=correct / len(pred) if pred else None,
                union_accuracy=correct / union if union else None)
