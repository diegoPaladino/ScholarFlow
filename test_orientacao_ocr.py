import ast
import os
import hashlib
from pathlib import Path
import tempfile
from typing import List, Dict, Tuple, Any
import unittest

from PIL import Image, ImageOps


class OrientacaoOcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {
            'carregar_imagem_ocr', 'preparar_caminhos_para_ocr', 'transformacao_selecao_ocr',
            'calcular_chave_cache_ocr_arquivos', 'calcular_hash_arquivo', 'obter_pasta_imagens'}]
        cls.env = dict(Image=Image, ImageOps=ImageOps, os=os, tempfile=tempfile,
                       List=List, Dict=Dict, Tuple=Tuple, Any=Any, hashlib=hashlib,
                       OCR_IA_REASONING_EFFORT='low',
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

    def test_manual_rotation_is_applied_before_crop_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'scan.png')
            source = Image.new('RGB', (80, 120), 'white')
            source.paste('red', (0, 0, 40, 60))
            source.save(path)
            original = Path(path).read_bytes()
            for angle in (90, 180, 270):
                for coords in (None, (5, 5, 30, 35)):
                    with self.subTest(angle=angle, coords=coords):
                        expected = source.rotate(-angle, expand=True)
                        if coords:
                            expected = expected.crop(coords)
                        processed, temporary = self.env['preparar_caminhos_para_ocr'](
                            [path], {path: {'coords': coords, 'rotacao': angle}})
                        try:
                            with Image.open(processed[0]) as sent:
                                self.assertEqual(sent.size, expected.size)
                                xy = (10, 10)
                                self.assertLess(max(abs(a-b) for a, b in
                                    zip(sent.getpixel(xy), expected.getpixel(xy))), 15)
                        finally:
                            for item in temporary:
                                os.remove(item)
            self.assertEqual(Path(path).read_bytes(), original)

    def test_rotation_and_crop_values_change_ocr_cache_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'scan.png')
            Image.new('RGB', (80, 120), 'white').save(path)
            key = self.env['calcular_chave_cache_ocr_arquivos']
            choices = [None, {'rotacao': 90, 'coords': None},
                       {'rotacao': 180, 'coords': None},
                       {'rotacao': 90, 'coords': (1, 2, 30, 40)},
                       {'rotacao': 90, 'coords': (2, 3, 30, 40)}]
            self.assertEqual(len({key([path], {path: choice}, 'modelo') for choice in choices}), 5)

    def test_rotation_buttons_update_preview_and_whole_image_selection(self):
        import tkinter as tk
        from tkinter import ttk
        from PIL import ImageTk
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'selecionar_regiao_ocr_em_janela')
        env = dict(self.env, tk=tk, ttk=ttk, ImageTk=ImageTk,
                   maximizar_janela_tk=lambda window: None, OCR_SELECTOR_CANCELLED=object())
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<preview>', 'exec'), env)
        root = tk.Tk()
        root.withdraw()
        try:
            def interagir(window):
                buttons = {child.cget('text'): child for frame in window.winfo_children()
                           for child in frame.winfo_children() if isinstance(child, ttk.Button)}
                canvas = next(child for child in window.winfo_children() if isinstance(child, tk.Canvas))
                buttons['Girar 90° à direita'].invoke()
                self.assertEqual((canvas.image.width(), canvas.image.height()), (120, 80))
                buttons['Girar 90° à esquerda'].invoke()
                self.assertEqual((canvas.image.width(), canvas.image.height()), (80, 120))
                buttons['Girar 90° à direita'].invoke()
                buttons['Imagem inteira'].invoke()
            root.wait_window = interagir
            with tempfile.TemporaryDirectory() as folder:
                path = str(Path(folder) / 'scan.png')
                Image.new('RGB', (80, 120), 'white').save(path)
                result = env['selecionar_regiao_ocr_em_janela'](root, path, 'Teste de giro')
                self.assertEqual(result, {'coords': None, 'rotacao': 90})
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
