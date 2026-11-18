import ast
import os
from pathlib import Path
import tempfile
from typing import List, Dict, Tuple
import unittest

from PIL import Image, ImageOps


class OrientacaoOcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {
            'carregar_imagem_ocr', 'preparar_caminhos_para_ocr'}]
        cls.env = dict(Image=Image, ImageOps=ImageOps, os=os, tempfile=tempfile,
                       List=List, Dict=Dict, Tuple=Tuple,
                       OCR_IMAGE_EXTENSIONS={'.jpg', '.png'},
                       OCR_IA_MAX_IMAGE_SIDE=2000, OCR_IA_JPEG_QUALITY=95)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<orientacao>', 'exec'), cls.env)

    def test_all_exif_orientations_match_visible_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            for orientation in range(1, 9):
                with self.subTest(orientation=orientation):
                    source = Image.new('RGB', (80, 120), 'white')
                    source.paste('red', (0, 0, 40, 60))
                    source.paste('blue', (40, 60, 80, 120))
                    exif = Image.Exif()
                    exif[274] = orientation
                    path = str(Path(folder) / 'scan.jpg')
                    source.save(path, exif=exif)
                    original = Path(path).read_bytes()
                    with Image.open(path) as raw:
                        expected = ImageOps.exif_transpose(raw).convert('RGB')
                    preview = self.env['carregar_imagem_ocr'](path)
                    self.assertEqual(preview.size, expected.size)
                    self.assertEqual(preview.tobytes(), expected.tobytes())
                    self.assertEqual(preview.getexif().get(274, 1), 1)
                    processed, temporary = self.env['preparar_caminhos_para_ocr']([path], {})
                    try:
                        with Image.open(processed[0]) as sent:
                            self.assertEqual(sent.size, expected.size)
                            self.assertEqual(sent.getexif().get(274, 1), 1)
                            for xy in ((10, 10), (sent.width - 10, sent.height - 10)):
                                self.assertLess(max(abs(a-b) for a, b in
                                                   zip(sent.getpixel(xy), expected.getpixel(xy))), 12)
                    finally:
                        for item in temporary:
                            os.remove(item)
                    self.assertEqual(Path(path).read_bytes(), original)

    def test_crop_coordinates_use_rotated_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'scan.jpg')
            source = Image.new('RGB', (80, 120), 'white')
            source.paste('red', (0, 0, 40, 60))
            exif = Image.Exif()
            exif[274] = 6
            source.save(path, exif=exif)
            # EXIF 6 places the upper-left red area at the upper-right.
            processed, temporary = self.env['preparar_caminhos_para_ocr'](
                [path], {path: (70, 5, 110, 30)})
            try:
                with Image.open(processed[0]) as cropped:
                    self.assertEqual(cropped.size, (40, 25))
                    red, green, blue = cropped.getpixel((20, 12))
                    self.assertGreater(red, 230)
                    self.assertLess(green, 25)
                    self.assertLess(blue, 25)
            finally:
                for item in temporary:
                    os.remove(item)


if __name__ == '__main__':
    unittest.main()
