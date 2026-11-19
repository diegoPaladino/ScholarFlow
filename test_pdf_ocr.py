import ast
import base64
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Tuple
import unittest
from unittest.mock import Mock

import pymupdf
from PIL import Image, ImageOps

from pdf_ocr import contar_paginas_pdf


class PdfOcrTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = str(Path(self.folder.name) / 'digitalizado.PDF')
        # Image-only PDF: no embedded text for a text extractor to recover.
        with pymupdf.open() as document:
            for color in ('red', 'blue'):
                page = document.new_page(width=72, height=108)
                import io
                image = io.BytesIO()
                Image.new('RGB', (100, 150), color).save(image, format='PNG')
                page.insert_image(page.rect, stream=image.getvalue())
            document.save(self.path)
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        names = {'carregar_imagem_ocr', 'transformacao_selecao_ocr',
                 'coletar_recortes_ocr', 'preparar_caminhos_para_ocr',
                 'calcular_chave_cache_ocr_arquivos', 'calcular_hash_arquivo',
                 'construir_conteudo_usuario_arquivos_openai'}
        self.env = dict(os=os, tempfile=tempfile, Image=Image, ImageOps=ImageOps,
                        List=List, Dict=Dict, Tuple=Tuple, Any=Any, hashlib=hashlib,
                        base64=base64, tk=Mock(), OCR_IMAGE_EXTENSIONS={'.png', '.jpg'},
                        OCR_SELECTOR_CANCELLED=object(), OCR_IA_MAX_IMAGE_SIDE=1200,
                        OCR_IA_JPEG_QUALITY=95, OCR_IA_REASONING_EFFORT='low')
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                                     and n.name in names], type_ignores=[]), '<pdf>', 'exec'), self.env)

    def test_scanned_pages_are_cropped_rotated_and_sent_as_images(self):
        original = Path(self.path).read_bytes()
        self.assertEqual(contar_paginas_pdf(self.path), 2)
        processed, temporary = self.env['preparar_caminhos_para_ocr'](
            [self.path], {self.path: {'paginas': [
                (10, 20, 60, 80), {'rotacao': 90, 'coords': None}]}})
        self.addCleanup(lambda: [os.remove(path) for path in temporary if os.path.exists(path)])
        self.assertEqual(len(processed), 2)
        for path, size, channel in zip(processed, [(50, 60), (300, 200)], [0, 2]):
            with Image.open(path) as image:
                self.assertEqual(image.size, size)
                self.assertGreater(image.getpixel((20, 20))[channel], 240)
        payload = self.env['construir_conteudo_usuario_arquivos_openai'](
            processed, 1000, '', '')
        self.assertEqual(sum(item['type'] == 'input_image' for item in payload), 2)
        self.assertEqual(Path(self.path).read_bytes(), original)

    def test_each_page_has_its_own_selection_and_cancel_stops_batch(self):
        selector = Mock(side_effect=[None, {'coords': (1, 2, 50, 60), 'rotacao': 90}])
        self.env['selecionar_regiao_ocr_em_janela'] = selector
        result = self.env['coletar_recortes_ocr'](None, [self.path], 'Documento')
        self.assertEqual(result[self.path]['paginas'][1]['rotacao'], 90)
        self.assertEqual([call.args[-1] for call in selector.call_args_list], [0, 1])
        selector.side_effect = [self.env['OCR_SELECTOR_CANCELLED']]
        self.assertIs(self.env['coletar_recortes_ocr'](None, [self.path], 'Historico'),
                      self.env['OCR_SELECTOR_CANCELLED'])

    def test_full_pdf_without_selection_and_cache_changes_per_page(self):
        processed, temporary = self.env['preparar_caminhos_para_ocr']([self.path], {})
        for path in temporary:
            os.remove(path)
        self.assertEqual(len(processed), 2)
        payload = self.env['construir_conteudo_usuario_arquivos_openai'](
            [self.path], 1000, '', '')
        self.assertEqual(sum(item['type'] == 'input_image' for item in payload), 2)
        key = self.env['calcular_chave_cache_ocr_arquivos']
        choices = [[None, None], [None, (1, 2, 30, 40)],
                   [None, {'rotacao': 90, 'coords': None}]]
        self.assertEqual(len({key([self.path], {self.path: {'paginas': choice}}, 'm')
                              for choice in choices}), 3)

    def test_password_protected_pdf_has_actionable_error(self):
        locked = str(Path(self.folder.name) / 'senha.pdf')
        with pymupdf.open(self.path) as document:
            document.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                          owner_pw='owner', user_pw='password')
        with self.assertRaisesRegex(ValueError, 'senha'):
            contar_paginas_pdf(locked)


if __name__ == '__main__':
    unittest.main()
