from contextlib import closing
import tempfile
import unittest
from idp_dataset import Dataset, SCHEMAS
from test_idp_dataset import example
from idp_benchmark_runner import run


class RunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.ds = Dataset(tmp.name)
        self.ref = example(SCHEMAS['boletim'])

    def add(self, doc=b'example', split='evaluation', group='a'*32):
        self.ds.register(doc, kind='boletim', split=split, group_id=group, reference=self.ref, reviewed=True)

    def test_empty(self):
        with self.assertRaises(ValueError): run(self.ds, lambda *_: self.ref)

    def test_perfect_and_partition(self):
        self.add(); self.add(b'learning', 'learning', 'b'*32)
        calls = []
        def extract(kind, doc):
            calls.append((kind, doc)); return self.ref
        r = run(self.ds, extract)
        self.assertEqual(calls, [('boletim', b'example')])
        self.assertEqual(r['accuracy'], 1)
        self.assertEqual(r['grade_accuracy'], 1)
        self.assertEqual(r['dataset_version'], self.ds.manifest('evaluation')['version'])
        self.assertNotIn('synthetic', str(r))

    def test_failure(self):
        self.add()
        def fail(*args): raise RuntimeError('private')
        r = run(self.ds, fail)
        self.assertEqual(r['failure_rate'], 1)
        self.assertEqual(r['accuracy'], 0)
        self.assertNotIn('private', str(r))

    def test_invalid(self):
        self.add(); r = run(self.ds, lambda *_: None)
        self.assertEqual(r['failures']['evaluation'], 1)
        self.assertEqual(r['counts']['missing'], r['counts']['expected_fields'])

    def test_grade_error(self):
        self.add(); actual = example(SCHEMAS['boletim']); actual['notas'][0]['nota'] = '0'
        r = run(self.ds, lambda *_: actual)
        self.assertEqual(r['grade_accuracy'], 0)
        self.assertEqual(r['counts']['wrong'], 1)

    def test_integrity(self):
        self.add()
        with closing(self.ds.connect()) as db, db:
            db.execute('UPDATE samples SET document=?', (b'changed',))
        with self.assertRaises(ValueError): run(self.ds, lambda *_: self.fail('called'))
