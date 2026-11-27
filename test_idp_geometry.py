import unittest
from io import BytesIO
from PIL import Image, ImageDraw
from idp_geometry import detect_grids

def image(grids=(),size=(600,500)):
    im=Image.new('RGB',size,'white'); d=ImageDraw.Draw(im)
    for xs,ys in grids:
        for x in xs: d.line((x,ys[0],x,ys[-1]),fill='black',width=3)
        for y in ys: d.line((xs[0],y,xs[-1],y),fill='black',width=3)
    b=BytesIO(); im.save(b,format='PNG'); return b.getvalue()
class GeometryTests(unittest.TestCase):
    def test_grid(self):
        g=detect_grids(image([([50,200,400],[50,100,150])]))['grids'][0]
        self.assertEqual((len(g['rows']),len(g['columns'])),(3,3)); self.assertAlmostEqual(g['columns'][1],200/600,places=2)
    def test_blank(self): self.assertEqual(detect_grids(image())['grids'],[])
    def test_two(self): self.assertEqual(len(detect_grids(image([([50,200,400],[50,100,150]),([50,200,400],[250,300,350])]))['grids']),2)
    def test_review(self): self.assertTrue(detect_grids(image())['needs_review'])
    def test_invalid(self):
        with self.assertRaises(ValueError): detect_grids(b'bad')
    def test_small(self):
        with self.assertRaises(ValueError): detect_grids(image(size=(20,20)))
    def test_single_box(self): self.assertEqual(detect_grids(image([([50,400],[50,150])]))['grids'],[])
    def test_normalized(self):
        g=detect_grids(image([([50,200,400],[50,100,150])]))['grids'][0]; self.assertTrue(all(0<=v<=1 for v in g['rows']+g['columns'])); self.assertTrue(g['needs_review'])
