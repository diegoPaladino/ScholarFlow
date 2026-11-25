import ast
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import idp_observability as obs


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'metrics.jsonl'
        p = patch.object(obs, 'LOG_PATH', self.path)
        p.start()
        self.addCleanup(p.stop)

    def events(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def test_success_and_usage(self):
        with obs.extraction('boletim', 'gpt-5-mini'):
            obs.record_attempt('requests')
            obs.record_attempt('urllib')
            obs.record_usage({'usage': {'input_tokens': 12, 'output_tokens': 3, 'total_tokens': 15}, 'secret': 'PRIVATE'})
        e, = self.events()
        self.assertTrue(e['success'])
        self.assertEqual((e['attempts'], e['requests_attempts'], e['urllib_attempts']), (2, 1, 1))
        self.assertEqual(e['total_tokens'], 15)
        self.assertGreaterEqual(e['duration_ms'], 0)
        self.assertNotIn('PRIVATE', self.path.read_text())

    def test_failure_preserves_exception_and_privacy(self):
        with self.assertRaisesRegex(RuntimeError, 'PRIVATE'):
            with obs.extraction('historico', 'PRIVATE'):
                raise RuntimeError('PRIVATE')
        e, = self.events()
        self.assertFalse(e['success'])
        self.assertEqual(e['error_category'], 'runtime_error')
        self.assertIsNone(e['input_tokens'])
        self.assertNotIn('PRIVATE', self.path.read_text())

    def test_write_failure_does_not_interrupt(self):
        with patch.object(obs, 'LOG_PATH', self.path / 'missing' / 'metrics.jsonl'):
            with obs.extraction('boletim', 'gpt-5-mini'):
                pass
            with self.assertRaises(ValueError):
                with obs.extraction('boletim', 'gpt-5-mini'):
                    raise ValueError('original')

    def test_concurrent_operations(self):
        def run(n):
            with obs.extraction('boletim', 'gpt-5-mini'):
                for _ in range(n):
                    obs.record_attempt('requests')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(run, range(1, 9)))
        events = self.events()
        self.assertEqual(sorted(e['attempts'] for e in events), list(range(1, 9)))
        self.assertEqual(len({e['operation_id'] for e in events}), 8)

    def test_unknown_usage_is_not_zero(self):
        with obs.extraction('historico', 'gpt-5-mini'):
            obs.record_usage({'usage': {'input_tokens': True, 'output_tokens': -1}})
        e, = self.events()
        self.assertIsNone(e['input_tokens'])
        self.assertIsNone(e['output_tokens'])

    def test_main_missing_key_instrumented(self):
        import os
        from typing import Any, Dict
        tree = ast.parse(Path(__file__).with_name('main.py').read_text(encoding='utf-8-sig'))
        names = ['extrair_campos_historico_com_openai', 'extrair_campos_boletim_com_openai', 'extrair_campos_documento_civil_com_openai']
        env = dict(os=os, Any=Any, Dict=Dict, OCR_IA_MODEL_PADRAO='gpt-5-mini')
        for name in names:
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<main>', 'exec'), env)
            with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
                with self.assertRaises(RuntimeError):
                    env[name]('unused')
        self.assertEqual(len(self.events()), 3)
        self.assertTrue(all(not e['success'] and e['attempts'] == 0 for e in self.events()))
