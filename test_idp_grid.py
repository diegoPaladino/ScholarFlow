import unittest
from idp_grid import reconstruct

def w(text,box): return {'text':text,'bbox':box,'confidence':None}
class GridTests(unittest.TestCase):
    def run_grid(self,words): return reconstruct({'page':1,'words':words},rows=[0,.5,1],columns=[0,.5,1])
    def test_assignment(self): self.assertEqual(self.run_grid([w('8',[.6,.6,.7,.7])])['cells'][1][1]['text'],'8')
    def test_zero(self): self.assertEqual(self.run_grid([w('0',[.1,.1,.2,.2])])['cells'][0][0]['text'],'0')
    def test_empty(self): self.assertIsNone(self.run_grid([])['cells'][0][0]['text'])
    def test_crossing(self): self.assertEqual(len(self.run_grid([w('8',[.4,.1,.6,.2])])['unresolved']),1)
    def test_order(self): self.assertEqual(self.run_grid([w('B',[.3,.1,.4,.2]),w('A',[.1,.1,.2,.2])])['cells'][0][0]['text'],'A B')
    def test_invalid_grid(self):
        with self.assertRaises(ValueError): reconstruct({'page':1,'words':[]},rows=[1,0],columns=[0,1])
    def test_invalid_box(self):
        with self.assertRaises(ValueError): self.run_grid([w('8',[0,0,2,1])])
    def test_review(self): self.assertTrue(self.run_grid([])['needs_review'])
