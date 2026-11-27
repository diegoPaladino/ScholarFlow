import unittest
from idp_geometry_score import assess_grid,rank_grids

def grid(rows=(.1,.3,.5),columns=(.1,.4,.7)):
    return dict(rows=rows,columns=columns)

class TestGeometryScore(unittest.TestCase):
    def test_regular(self):
        r=assess_grid(grid()); self.assertTrue(r['screening_pass']); self.assertEqual(r['cell_count'],4)
    def test_close_rows(self):
        self.assertIn('rows_close_boundaries',assess_grid(grid(rows=(.1,.101,.3,.5)))['flags'])
    def test_close_columns(self):
        self.assertIn('columns_close_boundaries',assess_grid(grid(columns=(.1,.101,.4,.7)))['flags'])
    def test_cell_limit(self):
        self.assertIn('cell_limit',assess_grid(grid(),max_cells=3)['flags'])
    def test_invalid(self):
        with self.assertRaises(ValueError): assess_grid(grid(rows=(.3,.1,.5)))
    def test_review(self):
        self.assertTrue(assess_grid(grid())['needs_review'])
    def test_rank(self):
        self.assertEqual(rank_grids([grid(rows=(.1,.101,.3,.5)),grid()])[0]['candidate_index'],1)
    def test_empty(self):
        self.assertEqual(rank_grids([]),[])
    def test_no_mutation(self):
        g=grid(); r=assess_grid(g); r['rows'].append(.9); self.assertEqual(g['rows'],(.1,.3,.5))
