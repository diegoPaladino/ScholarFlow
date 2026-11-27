import unittest
from idp_boletim_adapter import adapt_boletim
from idp_matrix_merge import merge_matrices

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.r=dict(ano=2026,bimestre=1,disciplina='MATEMÁTICA',kind='nota',value=0,sources=[])
        self.m=dict(records=[self.r],issues=[],needs_review=True)
    def adapt(self):
        return adapt_boletim(self.m,year=2026,numero_matricula='123456789',nome_aluno='Aluno fictício',turma='2 A')
    def test_zero(self):
        self.assertEqual(self.adapt()['payload']['notas'][0]['nota'],'0')
    def test_year(self):
        self.r['ano']=2025
        with self.assertRaises(ValueError): self.adapt()
    def test_duplicate(self):
        self.m['records'].append(self.r)
        with self.assertRaises(ValueError): self.adapt()
    def test_invalid(self):
        self.r['value']=float('nan')
        with self.assertRaises(ValueError): self.adapt()
    def test_review(self):
        self.assertFalse(self.adapt()['ready_for_submission'])
    def test_issues(self):
        self.m['issues']=[{'reason':'missing'}]
        self.assertEqual(self.adapt()['issues'],self.m['issues'])
    def test_evidence(self):
        self.assertIsNot(self.adapt()['evidence'][0],self.r)
    def test_merge(self):
        self.m=merge_matrices([dict(needs_review=True,issues=[],candidates=[dict(self.r,row=0,column=1)])])
        self.assertEqual(self.adapt()['payload']['notas'][0]['bimestre'],'1')
    def test_schema_keys(self):
        self.assertEqual(set(self.adapt()['payload']),{'numero_matricula','nome_aluno','ano','turma','notas'})
