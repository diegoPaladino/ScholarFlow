import unittest
from io import BytesIO
from unittest.mock import Mock
import fitz
from PIL import Image
from idp_local_ocr import extract_text


def pdf(text):
    with fitz.open() as d:
        p = d.new_page()
        p.insert_text((72,72), text)
        return d.tobytes()

class LocalOCRTests(unittest.TestCase):
    def test_native(self):
        ocr = Mock(side_effect=AssertionError)
        r = extract_text(pdf('HISTORICO ESCOLAR ALUNO FICTICIO'), ocr=ocr)
        self.assertEqual(r['pages'][0]['method'], 'native')
        self.assertIn('FICTICIO', r['text'])
        ocr.assert_not_called()
    def test_sparse(self):
        r = extract_text(pdf('A'), ocr=lambda image: 'TESTE')
        self.assertEqual(r['text'], 'TESTE')
        self.assertEqual(r['pages'][0]['method'], 'ocr')
    def test_force(self):
        r = extract_text(pdf('HISTORICO ESCOLAR ALUNO FICTICIO'), force_ocr=True, ocr=lambda image: 'OCR')
        self.assertEqual(r['text'], 'OCR')
    def test_image(self):
        b = BytesIO(); Image.new('RGB',(50,50)).save(b,format='PNG')
        self.assertTrue(extract_text(b.getvalue(), ocr=lambda image: '')['needs_review'])
    def test_invalid(self):
        for value in (b'', b'bad', 'bad'):
            with self.assertRaises(ValueError): extract_text(value)
    def test_page_limit(self):
        with fitz.open() as d:
            d.new_page(); d.new_page(); data=d.tobytes()
        with self.assertRaises(ValueError): extract_text(data,max_pages=1)
    def test_failure_propagates(self):
        with self.assertRaises(RuntimeError): extract_text(pdf('A'),ocr=Mock(side_effect=RuntimeError))
    def test_invalid_result(self):
        with self.assertRaises(TypeError): extract_text(pdf('A'),ocr=lambda image: None)
