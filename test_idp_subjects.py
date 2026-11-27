import unittest
from idp_subjects import extract_subjects


def run(text):
    return extract_subjects({'pages':[{'page':1,'text':text}]})


class SubjectTests(unittest.TestCase):
    def test_zero(self): self.assertEqual(run('Matemática: 0')['subjects']['MATEMÁTICA']['value'],'0')
    def test_decimal(self): self.assertEqual(run('Ciências 8,50')['subjects']['CIÊNCIAS']['value'],'8.5')
    def test_alias(self): self.assertIn('LÍNGUA PORTUGUESA',run('Português 9')['subjects'])
    def test_concept(self): self.assertEqual(run('Artes: B+')['subjects']['ARTES'],{'kind':'conceito','value':'B+'})
    def test_range(self): self.assertFalse(run('Artes: 10,1\nHistória: -1')['subjects'])
    def test_multiple(self): self.assertFalse(run('Artes 8 9 10')['subjects'])
    def test_conflict(self): self.assertFalse(run('Artes 8\nArtes 9')['subjects'])
    def test_repeat(self): self.assertEqual(run('Artes 8\nArtes 8,0')['subjects']['ARTES']['value'],'8')
    def test_invalid_duplicate(self): self.assertFalse(run('Artes 8\nArtes 99')['subjects'])
    def test_evidence(self):
        result=run('Cabeçalho\nEducação Física: 7'); e=result['candidates']['EDUCAÇÃO FÍSICA'][0]
        self.assertEqual((e['page'],e['line'],e['source']),(1,2,'Educação Física: 7')); self.assertTrue(result['needs_review'])
    def test_unknown(self): self.assertFalse(run('Observação Artes 8\nDisciplina desconhecida 9')['subjects'])
    def test_invalid_page(self):
        with self.assertRaises(ValueError): extract_subjects({'pages':[{'page':True,'text':''}]})
