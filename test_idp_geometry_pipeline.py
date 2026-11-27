import unittest
from io import BytesIO
from PIL import Image, ImageDraw
from idp_geometry_pipeline import propose, review_grid

def image(grid=True):
    im=Image.new('RGB',(400,300),'white'); d=ImageDraw.Draw(im)
    if grid:
        for x in (40,200,360): d.line((x,40,x,260),fill='black',width=2)
        for y in (40,150,260): d.line((40,y,360,y),fill='black',width=2)
    b=BytesIO(); im.save(b,format='PNG'); return b.getvalue()

def ocr(im):
    return dict(text=['0'],left=[80],top=[80],width=[10],height=[10],conf=[90])

class PipelineTests(unittest.TestCase):
    def test_candidates(self):
        r=propose(image(),ocr=ocr); self.assertTrue(r['candidates']); self.assertTrue(all(c['frame_id']==r['frame_id'] for c in r['candidates']))
    def test_review(self):
        r=propose(image(),ocr=ocr); g=review_grid(r,frame_id=r['frame_id'],rows=[0,.5,1],columns=[0,.5,1]); self.assertEqual(g['cells'][0][0]['text'],'0'); self.assertTrue(g['needs_review'])
    def test_mismatch(self):
        r=propose(image(),ocr=ocr)
        with self.assertRaises(ValueError): review_grid(r,frame_id='wrong',rows=[0,1],columns=[0,1])
    def test_empty(self):
        r=propose(image(False),ocr=ocr); self.assertEqual(r['candidates'],[]); self.assertTrue(r['needs_review'])
    def test_invalid(self):
        with self.assertRaises(ValueError): propose(b'bad',ocr=ocr)
    def test_same_image(self):
        seen=[]
        def recognize(im): seen.append(im.size); return ocr(im)
        r=propose(image(),ocr=recognize)
        with Image.open(BytesIO(r['image'])) as im: self.assertEqual(seen,[im.size])
