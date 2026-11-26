"""Offline benchmark orchestration; extractor receives only kind and document bytes."""
import json
import math
import statistics
import time
from contextlib import closing
from idp_dataset import canonical, digest, validate_reference
from idp_benchmark import evaluate, _flatten


def ratio(a, b):
    return a / b if b else None


def run(dataset, extractor):
    """Evaluate a fixed evaluation snapshot. No network or persistence by this module."""
    with closing(dataset.connect()) as db:
        rows = db.execute('SELECT sha,group_id,kind,reference,document FROM samples WHERE split=? ORDER BY sha', ('evaluation',)).fetchall()
    if not rows:
        raise ValueError('Empty evaluation partition')
    version = digest(canonical([1, 'evaluation', [r[:4] for r in rows]]).encode())
    # Validate the entire snapshot before invoking any extractor.
    for sha, _, kind, ref, doc in rows:
        if digest(doc) != sha:
            raise ValueError('Document integrity failure')
        validate_reference(kind, json.loads(ref))
    totals = dict(correct=0, wrong=0, missing=0, extra=0, expected_fields=0, predicted_fields=0)
    grades = dict(correct=0, expected=0)
    failures = dict(extraction=0, evaluation=0)
    times = []
    for _, _, kind, ref, doc in rows:
        expected = json.loads(ref)
        start = time.perf_counter()
        try:
            actual = extractor(kind, doc)
        except Exception:
            failures['extraction'] += 1
            actual = {}
        finally:
            times.append(time.perf_counter()-start)
        try:
            result = evaluate(expected, actual)
            pred = dict(_flatten(actual))
        except Exception:
            failures['evaluation'] += 1
            result = evaluate(expected, {})
            pred = {}
        for k in totals:
            totals[k] += result[k]
        for path, value in _flatten(expected):
            if path[-1] == 'nota' or (isinstance(path[-1], str) and path[-1].startswith('nota_')):
                grades['expected'] += 1
                grades['correct'] += int(path in pred and type(pred[path]) is type(value) and pred[path] == value)
    ordered = sorted(times)
    return dict(dataset_version=version, documents=len(rows), failures=failures,
                failure_rate=sum(failures.values())/len(rows), counts=totals,
                accuracy=ratio(totals['correct'], totals['expected_fields']),
                precision=ratio(totals['correct'], totals['predicted_fields']),
                union_accuracy=ratio(totals['correct'], totals['expected_fields']+totals['extra']),
                grade_accuracy=ratio(grades['correct'], grades['expected']), grade_counts=grades,
                latency_seconds=dict(mean=statistics.mean(times), p50=statistics.median(times), p95=ordered[math.ceil(.95*len(times))-1]))
