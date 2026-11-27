import unittest
from idp_historico_adapter import adapt_historico

class TestHistoryAdapter(unittest.TestCase):
    def row(self, **kw):
        return dict(dict(period_type='annual',ano='2025',serie='1'),**kw)
    def adapt(self,*rows):
        return adapt_historico(list(rows),numero_matricula='',nome_aluno='Synthetic')
    def test_zero(self):
        self.assertEqual(self.adapt(self.row(nota_arte='0'))['payload']['historicos'][0]['nota_arte'],'0')
    def test_concept(self):
        self.assertEqual(self.adapt(self.row(nota_arte='A'))['payload']['historicos'][0]['nota_arte'],'A')
    def test_missing(self):
        self.assertEqual(self.adapt(self.row())['payload']['historicos'][0]['nota_arte'],'')
    def test_period(self):
        with self.assertRaises(ValueError): self.adapt(self.row(period_type='bimonthly'))
    def test_duplicate(self):
        with self.assertRaises(ValueError): self.adapt(self.row(),self.row())
    def test_order(self):
        self.assertEqual([r['ano'] for r in self.adapt(self.row(ano='2026'),self.row())['payload']['historicos']],['2025','2026'])
    def test_review(self):
        self.assertFalse(self.adapt(self.row())['ready_for_submission'])
    def test_fallback(self):
        self.assertEqual(self.adapt(self.row())['payload']['ano'],'')
    def test_extras(self):
        self.assertEqual(self.adapt(self.row(disciplinas_extra=[dict(disciplina='Ingles',nota='7')]))['payload']['historicos'][0]['disciplinas_extra'][0]['nota'],'7')
