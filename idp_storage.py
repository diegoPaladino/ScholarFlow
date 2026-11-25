"""Local SQLite storage for non-content extraction metrics (schema v1)."""
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().with_name('idp_metrics.sqlite3')
FIELDS = ('operation_id', 'schema_version', 'timestamp', 'engine', 'document_type',
          'model', 'attempts', 'requests_attempts', 'urllib_attempts', 'input_tokens',
          'output_tokens', 'total_tokens', 'success', 'error_category', 'duration_ms')


def store(event, path=None):
    """Insert once per operation; unknown token counts remain SQL NULL."""
    values = tuple(event[k] for k in FIELDS)
    with closing(sqlite3.connect(str(DB_PATH if path is None else path), timeout=2)) as db:
        with db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported metrics database version')
            db.execute('''CREATE TABLE IF NOT EXISTS extraction_metrics (
                operation_id TEXT PRIMARY KEY NOT NULL, schema_version INTEGER NOT NULL,
                timestamp TEXT NOT NULL, engine TEXT NOT NULL, document_type TEXT NOT NULL,
                model TEXT NOT NULL, attempts INTEGER NOT NULL, requests_attempts INTEGER NOT NULL,
                urllib_attempts INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
                total_tokens INTEGER, success INTEGER NOT NULL CHECK(success IN (0,1)),
                error_category TEXT, duration_ms REAL NOT NULL CHECK(duration_ms >= 0))''')
            db.execute('CREATE INDEX IF NOT EXISTS idx_metrics_engine_type ON extraction_metrics(engine, document_type)')
            db.execute('PRAGMA user_version = 1')
            db.execute('INSERT INTO extraction_metrics (' + ','.join(FIELDS) + ') VALUES (' + ','.join('?' for _ in FIELDS) + ') ON CONFLICT(operation_id) DO NOTHING', values)
