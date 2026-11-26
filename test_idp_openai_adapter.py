import unittest
from pathlib import Path
from types import SimpleNamespace
from idp_openai_adapter import make_extractor, NAMES


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def mock(kind):
            def fn(paths, model):
                p = Path(paths[0]); self.calls.append((kind, p, p.read_bytes(), model))
                return {'kind': kind}
            return fn
        self.engine = SimpleNamespace(**{name: mock(kind) for kind, name in NAMES.items()})

    def adapter(self):
        return make_extractor(self.engine, model='test-model', allow_external=True)

    def test_default_denies(self):
        with self.assertRaises(PermissionError): make_extractor(self.engine, model='test-model')
        self.assertEqual(self.calls, [])

    def test_dispatch_and_cleanup(self):
        for kind, doc, ext in zip(NAMES, [b'%PDF-1.7', b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff'], ['.pdf','.png','.jpg']):
            self.assertEqual(self.adapter()(kind, doc), {'kind': kind})
            k, p, data, model = self.calls[-1]
            self.assertEqual((k,p.suffix,data,model),(kind,ext,doc,'test-model'))
            self.assertFalse(p.exists())

    def test_invalid_input(self):
        for kind, doc in [('unknown',b'%PDF-'), ('boletim',b'bad'), ('boletim','%PDF-')]:
            with self.assertRaises(ValueError): self.adapter()(kind, doc)
        self.assertEqual(self.calls, [])

    def test_cleanup_on_failure(self):
        def fail(paths, model):
            self.path = Path(paths[0]); raise RuntimeError('failure')
        self.engine.extrair_campos_boletim_com_openai = fail
        with self.assertRaises(RuntimeError): self.adapter()('boletim', b'%PDF-')
        self.assertFalse(self.path.exists())

    def test_model_required(self):
        with self.assertRaises(ValueError): make_extractor(self.engine, model='', allow_external=True)
