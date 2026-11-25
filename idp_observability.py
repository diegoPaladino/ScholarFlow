"""Local, best-effort extraction telemetry. No document contents are persisted."""
import contextvars
import json
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().with_name('idp_metrics.jsonl')
_CURRENT = contextvars.ContextVar('idp_operation', default=None)
_LOCK = threading.Lock()


def _model_name(value):
    # Do not persist arbitrary user-supplied model strings or fine-tune IDs.
    if isinstance(value, str) and re.fullmatch(r'(?:gpt-[0-9][a-z0-9.-]*|o[1-9][a-z0-9.-]*)', value) and len(value) <= 80:
        return value
    return 'other'


def _write(event):
    try:
        with _LOCK, LOG_PATH.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=True, allow_nan=False) + '\n')
    except Exception:
        # Telemetry must not replace the extraction result or exception.
        pass
    try:
        from idp_storage import store
        store(event, LOG_PATH.with_suffix(".sqlite3"))
    except Exception:
        # Independent sink: preserve extraction even if SQLite is unavailable.
        pass


@contextmanager
def extraction(document_type, model):
    event = dict(schema_version=1, operation_id=uuid.uuid4().hex,
                 timestamp=datetime.now(timezone.utc).isoformat(), engine='openai',
                 document_type=document_type if document_type in ('historico', 'boletim', 'documento_civil') else 'other',
                 model=_model_name(model), attempts=0, requests_attempts=0,
                 urllib_attempts=0, input_tokens=None, output_tokens=None,
                 total_tokens=None, success=False, error_category=None)
    start = time.perf_counter()
    token = _CURRENT.set(event)
    try:
        yield
        event['success'] = True
    except BaseException as exc:
        event['error_category'] = ('invalid_json' if isinstance(exc, json.JSONDecodeError)
                                   else 'file_not_found' if isinstance(exc, FileNotFoundError)
                                   else 'timeout' if isinstance(exc, TimeoutError)
                                   else 'invalid_value' if isinstance(exc, ValueError)
                                   else 'runtime_error' if isinstance(exc, RuntimeError)
                                   else 'other')
        raise
    finally:
        _CURRENT.reset(token)
        event['duration_ms'] = round((time.perf_counter() - start) * 1000, 3)
        _write(event)


def record_attempt(transport):
    event = _CURRENT.get()
    if event is not None and transport in ('requests', 'urllib'):
        event['attempts'] += 1
        event[transport + '_attempts'] += 1


def record_usage(response):
    event = _CURRENT.get()
    if event is None or not isinstance(response, dict):
        return
    usage = response.get('usage')
    if not isinstance(usage, dict):
        return
    for key in ('input_tokens', 'output_tokens', 'total_tokens'):
        value = usage.get(key)
        if type(value) is int and value >= 0:
            event[key] = value
