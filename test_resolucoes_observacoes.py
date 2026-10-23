import ast
from datetime import datetime
from pathlib import Path
import re
import unittest

from student_sync import normalizar


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        functions = {'normalizar_serie', 'corrigir_texto_utf8', 'reparar_acentos_mistos',
                     '_decodificar_texto_mojibake_misto', 'mover_continuidade_estudos_para_final'}
        nodes = [n for n in tree.body if
                 isinstance(n, ast.FunctionDef) and n.name in functions
                 or isinstance(n, ast.ClassDef) and n.name == 'ProcessamentoDeObservacoes'
                 or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                     (t.id.startswith('APARECIDA_') or t.id in {'ORDINAL_INDICATOR', 'MARCADORES_TEXTO_CORROMPIDO'})
                     for t in n.targets)]
        self.env = dict(re=re, datetime=datetime, normalizar_texto_busca=normalizar,
                        sessao_execucao={'matricula_atual': '123456789'},
                        exigir_ano_4_digitos=lambda ano: str(ano))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<observations>', 'exec'), self.env)
        self.processor = self.env['ProcessamentoDeObservacoes']()

    def generate(self, year, grade='1 ANO', city='APARECIDA DE GOIANIA', school='ESCOLA MUNICIPAL JARDIM BELA VISTA'):
        return self.processor.decisao_texto(str(year), school, city, 'nao', 'sim', '', grade)

    def test_first_and_second_grade_from_2026_use_numeric_resolution(self):
        for year in (2026, 2027):
            for grade in ('1 ANO', '2 ANO'):
                with self.subTest(year=year, grade=grade):
                    text = self.generate(year, grade)
                    self.assertIn(self.env['APARECIDA_RESOLUCAO_016_2026_TEXTO'], text)
                    self.assertTrue('011' in text or '011/2019' in text)
                    self.assertNotIn('nota apenas', text)
                    self.assertNotIn('Ficha Descritiva', text)

    def test_before_2026_and_other_grades_do_not_use_new_resolution(self):
        for year, grade in ((2025, '1 ANO'), (2025, '2 ANO'), (2026, '3 ANO'),
                            (2026, 'AGRUPAMENTO 4'), (2020, '1 ANO')):
            with self.subTest(year=year, grade=grade):
                text = self.generate(year, grade)
                self.assertNotIn('16/2026', text)
                self.assertIn('011', text)
                if year == 2025:
                    self.assertIn('nota apenas', text)

    def test_other_city_keeps_own_rules(self):
        text = self.generate(2026, city='GOIANIA', school='OUTRA ESCOLA')
        self.assertNotIn('16/2026', text)
        self.assertNotIn('nota apenas', text)

    def test_base_resolution_full_then_short_with_new_resolution_on_both_years(self):
        first = self.generate(2026)
        second = self.generate(2027, '2 ANO')
        self.assertIn(self.env['APARECIDA_RESOLUCAO_011_TEXTO_BASE'], first)
        self.assertNotIn(self.env['APARECIDA_RESOLUCAO_011_TEXTO_BASE'], second)
        self.assertIn(self.env['APARECIDA_RESOLUCAO_011_TEXTO_RESUMO'], second)
        for text in (first, second):
            self.assertEqual(text.count('16/2026'), 1)

    def test_special_2020_norms_are_preserved_alongside_base_resolution(self):
        text = self.generate(2020)
        self.assertIn('014', text)
        self.assertIn('011', text)

    def test_older_local_history_keeps_earlier_norm_alongside_011(self):
        text = self.generate(2018)
        self.assertIn('005/07', text)
        self.assertIn('011', text)
        self.assertNotIn('16/2026', text)

    def test_continuity_sentence_follows_both_resolutions(self):
        for grade in ('1 ANO', '2 ANO', '3 ANO'):
            with self.subTest(grade=grade):
                text = self.generate(2026, grade)
                self.assertRegex(text, r'Aluno\(a\) apto\(a\) a dar continuidade aos estudos no .+ ANO\.$')
                self.assertLess(text.index('011'), text.index('Aluno(a) apto(a)'))
                if grade in ('1 ANO', '2 ANO'):
                    self.assertLess(text.index('16/2026'), text.index('Aluno(a) apto(a)'))

    def test_continuity_moves_after_manual_observation_and_is_not_duplicated(self):
        ending = 'Aluno(a) apto(a) a dar continuidade aos estudos no 1º ANO.'
        text = f'Resolução 011/2019. {ending} Resolução 16/2026. {ending} Observação manual.'
        result = self.env['mover_continuidade_estudos_para_final'](text)
        self.assertEqual(result, f'Resolução 011/2019. Resolução 16/2026. Observação manual. {ending}')


if __name__ == '__main__':
    unittest.main()
