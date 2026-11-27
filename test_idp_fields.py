import unittest
from idp_fields import extract_fields

def run(*texts):
    return extract_fields({'pages':[{'page':i+1,'text':t} for i,t in enumerate(texts)]})

class FieldsTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(run('Matrícula: 0012\nNome do aluno: Pessoa Fictícia\nAno letivo: 2026')['fields'], {'numero_matricula':'0012','nome_aluno':'Pessoa Fictícia','ano':'2026'})
    def test_evidence(self):
        r=run('ignored\nUF: go'); self.assertEqual(r['candidates']['uf'][0],{'value':'GO','page':1,'line':2,'source':'UF: go','valid':True})
    def test_conflict(self):
        r=run('Ano letivo: 2025','Ano letivo: 2026'); self.assertNotIn('ano',r['fields']); self.assertEqual(r['issues'][0]['reason'],'conflicting_values')
    def test_repeat(self):
        self.assertEqual(run('Turma: A','Turma: A')['fields'],{'turma':'A'})
    def test_invalid(self):
        r=run('Matrícula: O12\nUF: XX\nData de nascimento: 31/02/2020'); self.assertEqual(r['fields'],{}); self.assertEqual(len(r['issues']),3)
    def test_mixed(self):
        self.assertNotIn('ano',run('Ano letivo: 2026','Ano letivo: ?')['fields'])
    def test_no_inference(self):
        r=run('ALUNO FICTICIO\nMATEMATICA 8.5\n2026'); self.assertEqual(r['fields'],{}); self.assertTrue(r['needs_review'])
    def test_date(self):
        self.assertEqual(run('Data de nascimento: 29/02/2020')['fields']['data_nascimento'],'29/02/2020')
    def test_invalid_page(self):
        with self.assertRaises(ValueError): extract_fields({'pages':[{'page':1,'text':'a'},{'page':1,'text':'b'}]})
    def test_empty(self):
        self.assertEqual(run('Nome do aluno:')['issues'],[{'field':'nome_aluno','reason':'invalid_value'}])
