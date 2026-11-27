import unittest
from io import BytesIO
from PIL import Image, ImageDraw
from idp_geometry_adaptive import detect_adaptive

def sample(partial=False,blank=False):
    im=Image.new('L',(600,400),255); d=ImageDraw.Draw(im)
    if not blank:
        for y in (60,120,180,240,300): d.line((60,y,540,y),fill=0,width=2)
        for x in (60,180,300,420,540): d.line((x,120 if partial and x==300 else 60,x,300),fill=0,width=2)
    b=BytesIO(); im.save(b,format='PNG'); return b.getvalue()
class AdaptiveTests(unittest.TestCase):
    def test_regular(self):
        g=detect_adaptive(sample())['grids']; self.assertEqual(len(g),1); self.assertEqual((len(g[0]['rows']),len(g[0]['columns'])),(5,5))
    def test_partial(self):
        g=detect_adaptive(sample(True))['grids']; self.assertEqual(len(g[0]['columns']),5)
    def test_blank(self): self.assertEqual(detect_adaptive(sample(blank=True))['grids'],[])
    def test_invalid(self):
        with self.assertRaises(ValueError): detect_adaptive(b'bad')
    def test_review(self): self.assertTrue(detect_adaptive(sample())['grids'][0]['needs_review'])
    def test_coordinates(self):
        g=detect_adaptive(sample())['grids'][0]; self.assertAlmostEqual(g['columns'][0],.1,delta=.01)
