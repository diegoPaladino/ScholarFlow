import unittest
from idp_matrix_semantics import interpret

def run(rows, **kw):
    args=dict(year=2026,subject_column=0,periods={1:1,2:2},first_row=0,last_row=len(rows)); args.update(kw)
    return interpret({'cells':[[{'text':x} for x in row] for row in rows]},**args)

class MatrixTests(unittest.TestCase):
    def test_zero(self): self.assertEqual(run([['MATEMÁTICA','0','6,5']])['records'][0]['value'],'0')
    def test_recovery_ignored(self): self.assertEqual(len(run([['CIÊNCIAS','5','6','7']])['records']),2)
    def test_missing(self): self.assertEqual(len(run([['CIÊNCIAS',None,'6']])['records']),1)
    def test_duplicate(self): self.assertEqual(run([['CIÊNCIAS','5','6'],['CIÊNCIAS','5','6']])['records'],[])
    def test_unknown(self): self.assertEqual(run([['UNKNOWN','5','6']])['records'],[])
    def test_alias(self): self.assertEqual(run([['ARTE','5','6']])['records'][0]['disciplina'],'ARTES')
    def test_invalid_mapping(self):
        with self.assertRaises(ValueError): run([['ARTE','5','6']],periods={1:1,2:1})
    def test_review(self): self.assertTrue(run([['ARTE','5','6']])['needs_review'])
    def test_status_not_grade(self): self.assertEqual(run([['ARTE','CS','-']])['records'],[])
