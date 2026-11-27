import unittest
from idp_tables import extract_tables

H='ANO LETIVO: 2026\nDISCIPLINA | 1º BIMESTRE | 2º BIMESTRE\n'
def run(text): return extract_tables({'pages':[{'page':1,'text':text}]})
class TableTests(unittest.TestCase):
    def test_values(self):
        r=run(H+'Matemática | 0 | 8,5'); self.assertEqual([x['value'] for x in r['records']],['0','8.5'])
    def test_year(self):
        r=run(H+'Artes | A | B\n'+H.replace('2026','2025')+'Artes | C | D'); self.assertEqual({x['ano'] for x in r['records']},{2025,2026})
    def test_no_year(self): self.assertFalse(run(H.split('\n',1)[1]+'Artes | A | B')['records'])
    def test_duplicate_header(self): self.assertFalse(run(H.replace('2º','1º')+'Artes | A | B')['records'])
    def test_conflict(self): self.assertEqual(len(run(H+'Artes | A | B\nArtes | C | B')['records']),1)
    def test_invalid(self): self.assertEqual(len(run(H+'Artes | 11 | 0')['records']),1)
    def test_blank(self): self.assertEqual(len(run(H+'Artes | | 0')['records']),1)
    def test_width(self): self.assertFalse(run(H+'Artes | A\nMatemática | 8 | 9')['records'])
    def test_page_reset(self): self.assertEqual(len(extract_tables({'pages':[{'page':1,'text':H+'Artes | A | B'},{'page':2,'text':'Matemática | 8 | 9'}]})['records']),2)
    def test_evidence(self):
        r=run(H+'Artes | A | B'); self.assertEqual(r['candidates'][0]['line'],3); self.assertTrue(r['needs_review'])
    def test_bad_page(self):
        with self.assertRaises(ValueError): extract_tables({'pages':[{'page':True,'text':''}]})
    def test_reversed(self): self.assertEqual(run(H.replace('1º BIMESTRE | 2º','2º BIMESTRE | 1º')+'Artes | A | B')['records'][0]['bimestre'],2)
