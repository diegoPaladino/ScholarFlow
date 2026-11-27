import unittest
from io import BytesIO
from idp_spatial import extract_spatial
from PIL import Image
import fitz

def png():
    b=BytesIO(); Image.new('RGB',(100,100),'white').save(b,format='PNG'); return b.getvalue()
def data(): return dict(text=['6,0',''],left=[10,0],top=[20,0],width=[20,0],height=[10,0],conf=['90','-1'])
def pdf(rotation=0):
    with fitz.open() as d:
        p=d.new_page(); p.insert_text((50,50),'Matematica Ciencias Historia 2026'); p.set_rotation(rotation); return d.tobytes()
class SpatialTests(unittest.TestCase):
    def test_image(self):
        w=extract_spatial(png(),ocr=lambda _:data())['pages'][0]['words']; self.assertEqual(w,[dict(text='6,0',bbox=[.1,.2,.3,.3],confidence=.9)])
    def test_native(self):
        p=extract_spatial(pdf())['pages'][0]; self.assertEqual(p['method'],'native'); self.assertIsNone(p['words'][0]['confidence'])
    def test_rotation(self):
        p=extract_spatial(pdf(90))['pages'][0]; self.assertEqual(len(p['words']),4); self.assertGreater(p['words'][0]['bbox'][0],.8)
    def test_force(self): self.assertEqual(extract_spatial(pdf(),force_ocr=True,ocr=lambda _:data())['pages'][0]['method'],'ocr')
    def test_invalid(self):
        with self.assertRaises(ValueError): extract_spatial(b'bad')
    def test_limits(self):
        with self.assertRaises(ValueError): extract_spatial(png(),dpi=500)
    def test_columns(self):
        d=data(); d['conf']=[]
        with self.assertRaises(ValueError): extract_spatial(png(),ocr=lambda _:d)
    def test_review(self): self.assertTrue(extract_spatial(png(),ocr=lambda _:data())['needs_review'])
    def test_outside(self):
        d=data(); d['left'][0]=99; self.assertEqual(extract_spatial(png(),ocr=lambda _:d)['pages'][0]['words'],[])
    def test_failure(self):
        def fail(_): raise RuntimeError('OCR failed')
        with self.assertRaises(RuntimeError): extract_spatial(png(),ocr=fail)
