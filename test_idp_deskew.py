import unittest
import cv2
import numpy as np
from idp_deskew import deskew

def sample(angle=0):
    im=np.full((500,700),255,np.uint8)
    for y in range(100,401,50): cv2.line(im,(80,y),(620,y),0,2)
    for x in range(80,621,90): cv2.line(im,(x,100),(x,400),0,2)
    im=cv2.warpAffine(im,cv2.getRotationMatrix2D((350,250),angle,1),(700,500),borderValue=255)
    return cv2.imencode('.png',im)[1].tobytes()
class DeskewTests(unittest.TestCase):
    def test_positive(self): self.assertAlmostEqual(deskew(sample(5))['angle'],-5,delta=.5)
    def test_negative(self): self.assertAlmostEqual(deskew(sample(-5))['angle'],5,delta=.5)
    def test_straight(self): self.assertEqual(deskew(sample())['angle'],0)
    def test_blank(self): self.assertEqual(deskew(cv2.imencode('.png',np.full((100,100),255,np.uint8))[1].tobytes())['angle'],0)
    def test_invalid(self):
        with self.assertRaises(ValueError): deskew(b'bad')
    def test_output(self):
        r=deskew(sample(5)); self.assertTrue(r['needs_review']); self.assertEqual(len(r['matrix']),2); self.assertTrue(r['image'].startswith(b'\x89PNG')); self.assertGreater(cv2.imdecode(np.frombuffer(r['image'],np.uint8),0).shape[1],700)
