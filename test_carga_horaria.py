import ast
from pathlib import Path
import re
import unittest
from unittest.mock import Mock


class CargaHorariaTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FuncoesDoPrograma')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {
            'preencher_carga_horaria', 'conferir_carga_horaria', 'garantir_etapa_disciplinas'}]
        self.field = Mock()
        self.field.input_value.return_value = '800'
        self.env = dict(re=re, _build_locator=lambda *args: self.field, By=Mock(),
                        _garantir_locator_visivel=Mock(), _get_base=lambda p: p,
                        sessao_execucao={'historico_alvo': {}}, registrar_etapa_historico=Mock())
        exec(compile(ast.Module(body=methods, type_ignores=[]), '<carga>', 'exec'), self.env)
        self.env['FuncoesDoPrograma'] = Mock(**{n.name: self.env[n.name] for n in methods})

    def test_fill_commits_events_and_confirms_value(self):
        self.env['preencher_carga_horaria'](Mock(), '800')
        self.field.fill.assert_called_once_with('800')
        self.field.dispatch_event.assert_called_once_with('change')
        self.field.press.assert_called_once_with('Tab')
        self.assertEqual(self.env['sessao_execucao']['carga_horaria_esperada'], '800')

    def test_invalid_or_missing_hours_rejected(self):
        for value in ('', None, '0', '-1', 'abc'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.env['preencher_carga_horaria'](Mock(), value)
        self.field.fill.assert_not_called()

    def test_field_reset_by_page_rejected(self):
        for value in ('', '0', '200'):
            self.field.input_value.return_value = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                self.env['preencher_carga_horaria'](Mock(), '800')

    def test_reset_before_header_save_prevents_submission(self):
        page = Mock(url='https://example.test/sca_historico_escolar_novo.asp')
        page.locator.return_value.first.count.return_value = 0
        self.env['sessao_execucao']['carga_horaria_esperada'] = '800'
        self.field.input_value.return_value = ''
        with self.assertRaises(RuntimeError):
            self.env['garantir_etapa_disciplinas'](page)
        page.get_by_role.return_value.first.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
