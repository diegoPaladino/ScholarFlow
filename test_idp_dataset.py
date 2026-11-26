import tempfile
import unittest
from idp_dataset import Dataset, SCHEMAS


def example(schema):
    if schema['type']=='string': return 'synthetic'
    if schema['type']=='array': return [example(schema['items'])]
    return {k:example(v) for k,v in schema['properties'].items()}


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.ds=Dataset(self.tmp.name)
        self.kw=dict(kind='boletim',split='evaluation',group_id='a'*32,reference=example(SCHEMAS['boletim']),reviewed=True)

    def add(self, doc=b'synthetic', **kw):
        return self.ds.register(doc, **(self.kw | kw))

    def test_all_types(self):
        for kind in SCHEMAS: self.add(kind.encode(),kind=kind,reference=example(SCHEMAS[kind]))
        self.assertEqual(self.ds.manifest('evaluation')['count'],3)

    def test_duplicate(self):
        self.assertEqual(self.add(),self.add()); self.assertEqual(self.ds.manifest('evaluation')['count'],1)

    def test_cross_partition_document(self):
        self.add()
        with self.assertRaises(ValueError): self.add(split='learning',group_id='b'*32)

    def test_cross_partition_group(self):
        self.add()
        with self.assertRaises(ValueError): self.add(b'other',split='learning')

    def test_review_required(self):
        with self.assertRaises(ValueError): self.add(reviewed=False)

    def test_schema(self):
        with self.assertRaises(ValueError): self.add(reference={})

    def test_duplicate_rows(self):
        ref=self.kw['reference']; ref['notas']*=2
        with self.assertRaises(ValueError): self.add(reference=ref)

    def test_manifest(self):
        before=self.ds.manifest('evaluation'); self.add(); after=self.ds.manifest('evaluation')
        self.assertNotEqual(before['version'],after['version']); self.assertEqual(after,Dataset(self.tmp.name).manifest('evaluation'))
        self.assertNotIn('synthetic',str(after))
        self.add(b'other',split='learning',group_id='b'*32); self.assertEqual(after,self.ds.manifest('evaluation'))
