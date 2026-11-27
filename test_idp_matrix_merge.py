import unittest
from idp_matrix_merge import merge_matrices


def matrix(year=2025, period=1, value=0, kind='nota'):
    return dict(needs_review=True, issues=[], candidates=[dict(ano=year,bimestre=period,disciplina='ARTES',kind=kind,value=value,row=1,column=2)])


class MergeTests(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(merge_matrices([matrix()])['records'][0]['value'],0)
    def test_years(self):
        self.assertEqual(len(merge_matrices([matrix(),matrix(2026)])['records']),2)
    def test_periods(self):
        self.assertEqual(len(merge_matrices([matrix(),matrix(period=2)])['records']),2)
    def test_conflict(self):
        self.assertFalse(merge_matrices([matrix(),matrix(value=8)])['records'])
    def test_duplicate(self):
        self.assertFalse(merge_matrices([matrix(),matrix()])['records'])
    def test_missing(self):
        self.assertFalse(merge_matrices([matrix(),matrix(value=None,kind=None)])['records'])
    def test_provenance(self):
        self.assertEqual(merge_matrices([matrix()])['records'][0]['sources'],[dict(matrix=0,row=1,column=2)])
    def test_invalid(self):
        with self.assertRaises(ValueError): merge_matrices([matrix(period=5)])
    def test_review(self):
        self.assertTrue(merge_matrices([])['needs_review'])
    def test_issue(self):
        m=matrix(); m['issues']=[{'reason':'unknown_subject'}]
        self.assertEqual(merge_matrices([m])['issues'][0]['detail']['reason'],'unknown_subject')
