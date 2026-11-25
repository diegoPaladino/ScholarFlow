import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import idp_observability as obs
import idp_storage as storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.log = Path(folder.name) / 'metrics.jsonl'
        self.db = self.log.with_suffix('.sqlite3')
        p = patch.object(obs, 'LOG_PATH', self.log)
        p.start()
        self.addCleanup(p.stop)

    def rows(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM extraction_metrics')]

    def test_dual_sink_and_null(self):
        with obs.extraction('boletim', 'gpt-5-mini'):
            obs.record_usage({'usage': {'output_tokens': 0}})
        row, = self.rows()
        self.assertIsNone(row['input_tokens'])
        self.assertEqual(row['output_tokens'], 0)
        self.assertEqual(row['success'], 1)
        self.assertIn(row['operation_id'], self.log.read_text())

    def test_idempotent(self):
        with obs.extraction('historico', 'gpt-5-mini'):
            pass
        row, = self.rows()
        storage.store(row, self.db)
        self.assertEqual(len(self.rows()), 1)

    def test_failure_privacy(self):
        with self.assertRaises(ValueError):
            with obs.extraction('historico', 'PRIVATE'):
                raise ValueError('PRIVATE')
        row, = self.rows()
        self.assertEqual(row['success'], 0)
        self.assertNotIn('PRIVATE', str(row))

    def test_sqlite_failure_keeps_jsonl(self):
        with patch.object(storage, 'store', side_effect=sqlite3.OperationalError):
            with obs.extraction('boletim', 'gpt-5-mini'):
                pass
        self.assertTrue(self.log.exists())

    def test_jsonl_failure_keeps_sqlite(self):
        self.log.mkdir()
        with obs.extraction('boletim', 'gpt-5-mini'):
            pass
        self.assertEqual(len(self.rows()), 1)

    def test_concurrency(self):
        def run(_):
            with obs.extraction('boletim', 'gpt-5-mini'):
                pass
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(run, range(12)))
        self.assertEqual(len(self.rows()), 12)

    def test_unknown_schema_preserved(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA user_version=99')
        with obs.extraction('boletim', 'gpt-5-mini'):
            pass
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 99)
        self.assertTrue(self.log.exists())
