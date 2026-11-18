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
            'normalizar_carga_horaria', 'preencher_carga_horaria', 'conferir_carga_horaria', 'garantir_etapa_disciplinas'}]
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
        for value in ('', None, '0', '-1', 'abc', '833h60min', '833:99', '833:', '10000', 'NaN'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.env['preencher_carga_horaria'](Mock(), value)
        self.field.fill.assert_not_called()

    def test_duration_and_decimal_formats_are_converted_before_filling(self):
        for value, expected in (
            ('833h20min', '833'), ('833 h 20 min', '833'),
            ('833 horas 20 minutos', '833'), ('833:20', '833'),
            ('833h30min', '834'), ('800h', '800'), ('800 horas', '800'),
            ('833,33', '833'), ('833.5', '834'), ('1000', '1000'),
        ):
            with self.subTest(value=value):
                self.field.reset_mock()
                self.field.input_value.return_value = expected
                self.env['preencher_carga_horaria'](Mock(), value)
                self.field.fill.assert_called_once_with(expected)
                self.assertEqual(self.env['sessao_execucao']['carga_horaria_esperada'], expected)
                self.env['registrar_etapa_historico'].assert_called_with(
                    'carga_horaria_preenchida', unittest.mock.ANY,
                    carga_horaria=expected, carga_horaria_original=value)

    def test_field_reset_by_page_rejected(self):
        for value in ('', '0', '200'):
            self.field.input_value.return_value = value
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                self.env['preencher_carga_horaria'](Mock(), '800')

    def test_interface_displays_numeric_value_for_imported_and_manual_hours(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in {
            'definir_carga_horaria_interface', 'normalizar_campo_carga_horaria'}]
        variable = Mock()
        self.env.update(carga_horaria_var=variable, status_scan_var=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<interface>', 'exec'), self.env)
        self.assertTrue(self.env['definir_carga_horaria_interface']('833h20min'))
        variable.set.assert_called_with('833')
        variable.get.return_value = '833:30'
        self.assertTrue(self.env['normalizar_campo_carga_horaria']())
        variable.set.assert_called_with('834')
        self.assertFalse(self.env['definir_carga_horaria_interface']('invalido'))
        variable.set.assert_called_with('')

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
