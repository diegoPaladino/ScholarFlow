import unittest
from idp_boletim_adapter import adapt_boletim
from idp_boletim_contract import validate_review


class ContractTests(unittest.TestCase):
    def review(self):
        return adapt_boletim(dict(records=[dict(ano=2026,bimestre=1,disciplina='MATEMÁTICA',kind='nota',value=0),dict(ano=2026,bimestre=2,disciplina='LÍNGUA PORTUGUESA',kind='nota',value=7.5)],issues=[{'reason':'review'}],needs_review=True),year=2026,numero_matricula='123',nome_aluno='Aluno Sintético',turma='2 A')
    def validate(self, r, **kwargs):
        return validate_review(r, **dict(dict(matricula='123456789',nome_esperado='Aluno Sintético',year=2026),**kwargs))
    def test_zero_decimal(self):
        self.assertEqual([x['nota'] for x in self.validate(self.review())['payload']['notas']], ['0','7.5'])
    def test_year(self):
        with self.assertRaises(ValueError): self.validate(self.review(),year=2025)
    def test_name(self):
        with self.assertRaises(ValueError): self.validate(self.review(),nome_esperado='Outra Pessoa')
    def test_empty_name(self):
        with self.assertRaises(ValueError): self.validate(self.review(),nome_esperado='')
    def test_registration(self):
        self.assertEqual(self.validate(self.review())['payload']['numero_matricula_origem'],'123')
    def test_review_only(self):
        r=self.review(); out=self.validate(r); self.assertFalse(out['ready_for_submission']); self.assertTrue(out['needs_review']); self.assertEqual(out['issues'],r['issues']); self.assertEqual(out['evidence'],r['evidence']); out['evidence'].clear(); self.assertTrue(r['evidence'])
    def test_dropped_grade(self):
        r=self.review(); r['payload']['notas'][0]['disciplina']='DESCONHECIDA'
        with self.assertRaises(ValueError): self.validate(r)
    def test_invalid_registration(self):
        with self.assertRaises(ValueError): self.validate(self.review(),matricula='123')
