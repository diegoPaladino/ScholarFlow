import ast
import difflib
from pathlib import Path
import re
import unittest
import unicodedata
from typing import Any, Dict, List


class DocumentComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        names = {'normalizar_texto_busca', 'normalizar_data_comparacao',
                 'comparar_valor_documento', 'comparar_documento_com_rel_aluno'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        cls.env = dict(re=re, difflib=difflib, unicodedata=unicodedata, Any=Any,
                       Dict=Dict, List=List, corrigir_texto_utf8=lambda text: text)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<comparison>', 'exec'), cls.env)

    def setUp(self):
        self.student = dict(matricula='202600001', nome_aluno='ALUNA TESTE', sexo='F',
                            data_nascimento='01/01/2015', naturalidade='GOIÂNIA',
                            mae='MAE TESTE', pai='PAI TESTE')
        self.document = dict(self.student, naturalidade='Goiânia-GO')

    def compare(self, preferencial='202600001'):
        return self.env['comparar_documento_com_rel_aluno'](self.document, [self.student], preferencial)

    def test_all_equal_has_bounded_score_and_no_detailed_repetition(self):
        result = self.compare()
        self.assertAlmostEqual(result['score'], 1.0)
        self.assertEqual(result['divergencias'], [])
        self.assertIn('Nenhuma divergencia', result['resumo'])
        self.assertNotIn('ALUNA TESTE', result['resumo'])
        self.assertNotIn('Campos coincidentes', result['resumo'])

    def test_only_mismatches_are_in_summary(self):
        self.document['pai'] = 'OUTRO PAI'
        result = self.compare()
        self.assertIn('OUTRO PAI', result['resumo'])
        self.assertIn('PAI TESTE', result['resumo'])
        self.assertNotIn('MAE TESTE', result['resumo'])
        self.assertGreaterEqual(result['score'], 0)
        self.assertLessEqual(result['score'], 1)

    def test_missing_field_is_explicit_and_score_is_bounded_without_matricula(self):
        self.document['pai'] = ''
        result = self.compare('')
        self.assertIn('nao informado', result['resumo'])
        self.assertIn('Pai', result['ausentes'])
        self.assertLessEqual(result['score'], 1)

    def test_no_candidates_is_zero(self):
        result = self.env['comparar_documento_com_rel_aluno'](self.document, [])
        self.assertEqual(result['score'], 0)
        self.assertIsNone(result['registro'])

    def test_different_explicit_states_are_not_hidden(self):
        self.student['naturalidade'] = 'Goiânia/SP'
        self.assertIn('Naturalidade', self.compare()['resumo'])
