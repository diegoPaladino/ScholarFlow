import ast
import unittest
from pathlib import Path
from unittest.mock import Mock

class InterfaceFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))

    def test_mixed_portuguese_accents(self):
        names = {'reparar_acentos_mistos', 'corrigir_texto_utf8', '_decodificar_texto_mojibake_misto'}
        nodes = [n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        env = {'MARCADORES_TEXTO_CORROMPIDO': tuple(map(chr, (195, 194, 226, 240, 65533)))}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<encoding>', 'exec'), env)
        correct = 'Educa\u00e7\u00e3o B\u00e1sica, autoriza\u00e7\u00e3o e institui\u00e7\u00f5es'
        broken = correct.encode('utf-8').decode('latin-1')
        mixed = 'Resolu\u00e7\u00e3o CME: ' + broken + '. Goi\u00e2nia.'
        expected = 'Resolu\u00e7\u00e3o CME: ' + correct + '. Goi\u00e2nia.'
        repair = env['corrigir_texto_utf8']
        self.assertEqual(repair(mixed), expected)
        self.assertEqual(repair(expected), expected)
        self.assertEqual(repair(broken.encode('utf-8').decode('cp1252')), correct)

    def transition(self, present=False, scroll_error=False):
        node = next(n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)
                    and n.name == 'garantir_etapa_disciplinas')
        env = {'_get_base': lambda page: page, 'PlaywrightTimeoutError': TimeoutError,
               'sessao_execucao': {'historico_alvo': {}, 'carga_horaria_esperada': '800'},
               'FuncoesDoPrograma': Mock(),
               'registrar_etapa_historico': Mock(), 'abrir_disciplinas_registro': Mock()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<navigation>', 'exec'), env)
        page = Mock(url='https://example.test/app/sca_historico_escolar_novo.asp')
        discipline = page.locator.return_value.first
        discipline.count.return_value = int(present)
        button = page.get_by_role.return_value.first
        if scroll_error:
            button.scroll_into_view_if_needed.side_effect = [TimeoutError(), None]
        env['garantir_etapa_disciplinas'](page)
        return page, discipline, button

    def test_match_year_series_school_and_reject_duplicates(self):
        import re
        import student_sync
        names = {'indice_registro_historico', 'normalizar_serie'}
        nodes = [n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        env = dict(re=re, normalizar_texto_busca=student_sync.normalizar, ORDINAL_INDICATOR=chr(186))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<selection>', 'exec'), env)
        rows = [['2025', 'Anual', 'ESCOLA A', 'ENSINO FUNDAMENTAL', '3 ANO'],
                ['2026', 'Anual', 'ESCOLA A', 'ENSINO FUNDAMENTAL', '2 ANO'],
                ['2026', 'Anual', 'ESCOLA B', 'ENSINO FUNDAMENTAL', '3 ANO'],
                ['2026', 'Anual', 'ESCOLA A', 'ENSINO FUNDAMENTAL', '3 ANO']]
        select = env['indice_registro_historico']
        self.assertEqual(select(rows, '2026', '3 ANO', 'ESCOLA A'), 3)
        self.assertIsNone(select(rows, '2024', '3 ANO', 'ESCOLA A'))
        with self.assertRaises(RuntimeError):
            select(rows + [rows[-1]], '2026', '3 ANO', 'ESCOLA A')

    def test_saved_html_matches_target(self):
        from html.parser import HTMLParser
        class Rows(HTMLParser):
            def __init__(self):
                super().__init__(); self.rows = []; self.row = None; self.cell = None
            def handle_starttag(self, tag, attrs):
                if tag == 'tr': self.row = []
                if tag == 'td' and self.row is not None: self.cell = ''
            def handle_data(self, data):
                if self.cell is not None: self.cell += data
            def handle_endtag(self, tag):
                if tag == 'td' and self.cell is not None:
                    self.row.append(self.cell.strip()); self.cell = None
                if tag == 'tr' and self.row is not None:
                    self.rows.append(self.row); self.row = None
        parser = Rows()
        parser.feed(Path('HTML-GEMUL_POS_LANCAMENTO-DISCIPLINAS.txt').read_text(encoding='utf-8-sig'))
        matching = [row for row in parser.rows if len(row) >= 5 and row[0] == '2026']
        self.assertTrue(any(row[2] == 'ESCOLA MUNICIPAL JARDIM BELA VISTA' and '3' in row[4] for row in matching))

    def test_initial_form_saved_before_waiting_for_disciplines(self):
        page, discipline, button = self.transition()
        button.scroll_into_view_if_needed.assert_called_once()
        button.click.assert_called_once()
        discipline.wait_for.assert_called_once_with(state='attached', timeout=15000)

    def test_existing_disciplines_do_not_submit_again(self):
        page, discipline, button = self.transition(present=True)
        button.click.assert_not_called()

    def test_page_down_fallback(self):
        page, discipline, button = self.transition(scroll_error=True)
        page.keyboard.press.assert_called_with('PageDown')
        button.click.assert_called_once()

if __name__ == '__main__':
    unittest.main()


class CourseSelectionTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SelecionarCurso')
        from playwright.sync_api import Error, sync_playwright
        self.play = sync_playwright().start()
        self.browser = self.play.chromium.launch(headless=True)
        self.page = self.browser.new_page()
        env = dict(_get_base=lambda page: page, PlaywrightError=Error,
                   _normalizar_rotulo_interface=lambda text: text.strip().upper())
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<course>', 'exec'), env)
        self.selector = env['SelecionarCurso'](self.page)
        self.selector._sincronizar_campo_txtcurso = Mock()

    def tearDown(self):
        self.browser.close()
        self.play.stop()

    def test_already_selected_does_not_dispatch_change(self):
        self.page.set_content("""<select id="cmbCurso" onchange="window.changes++">
            <option value="999" selected>EF-ENSINO FUNDAMENTAL</option></select>
            <script>window.changes=0</script>""")
        self.selector._selecionar_curso_por_valor('80', 'EF-ENSINO FUNDAMENTAL')
        self.assertEqual(self.page.evaluate('window.changes'), 0)

    def test_course_navigation_is_selected_once_with_actual_option_value(self):
        loads = []
        def serve(route):
            selected = route.request.url.endswith('/selected')
            loads.append(selected)
            route.fulfill(content_type='text/html', body=
                '<select id="cmbCurso" onchange="location.href=&quot;/selected&quot;">'
                '<option value="0">Selecione</option>'
                '<option value="999" ' + ('selected' if selected else '') +
                '>EF-ENSINO FUNDAMENTAL</option></select>')
        self.page.route('**/*', serve)
        self.page.goto('https://course.test/start')
        self.selector._selecionar_curso_por_valor('80', 'EF-ENSINO FUNDAMENTAL')
        self.assertEqual(self.page.locator('#cmbCurso').input_value(), '999')
        self.assertEqual(loads, [False, True])


class CacheRestoreTests(unittest.TestCase):
    def test_form_restore_loads_ocr_years_then_overlays_manual_values(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == 'aplicar_cache_formulario_da_matricula')
        import re
        from typing import Any
        env = dict(Any=Any, re=re)
        # UI collaborators are mocked; exercise the actual restore function.
        for name in {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}:
            if name not in env and name not in dir(__builtins__):
                env[name] = Mock()
        import builtins
        env.update(vars(builtins))
        env.update(str=str, bool=bool, isinstance=isinstance, dict=dict, list=list,
                   Exception=Exception, disciplinas_vars={}, dados={}, bloqueio_auto={'ativo': False})
        env['carregar_cache_formulario_por_matricula'].return_value = {
            'dados_formulario': {'ano': '2024', 'nome_aluno': 'ALUNO', 'carga_horaria': '800'}}
        restored = []
        env['aplicar_cache_historico_da_matricula'].side_effect = lambda *a, **kw: restored.append('ocr')
        env['ano_var'].set.side_effect = lambda value: restored.append(value)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<restore>', 'exec'), env)
        self.assertTrue(env[node.name]('202626234'))
        self.assertEqual(restored[:2], ['ocr', '2024'])


class YearSelectionTests(unittest.TestCase):
    def setUp(self):
        from datetime import datetime
        self.current = str(datetime.now().year)
        self.previous = str(datetime.now().year - 1)
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'on_ano_change')
        self.grades = {'ARTES': Mock(), 'CIENCIAS': Mock()}
        self.histories = {self.previous: {'nota_arte': '9.5'}, self.current: {'nota_arte': '8.0'}}
        self.env = dict(datetime=datetime, bloqueio_auto={'ativo': False},
            extrair_ano_4_digitos=lambda text: text, ano_var=Mock(),
            historicos_por_ano=self.histories, disciplinas_vars=self.grades,
            dados={'disciplinas_extra': [{'disciplina': 'Extra', 'nota': '9'}]},
            definir_texto_observacoes=Mock(), definir_texto_observacoes_gerais=Mock(),
            observacoes_var=Mock(), marcar_disciplinas_var=Mock(), ficha_descritiva_var=Mock(),
            cursando_var=Mock(), mostrar_disciplinas=Mock(), on_transfer_date_change=Mock(),
            aplicar_historico_por_ano=Mock(return_value=True))
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<year-change>', 'exec'), self.env)

    def test_selecting_current_year_clears_fields_even_with_ocr_for_that_year(self):
        self.env['ano_var'].get.return_value = self.current
        self.env['on_ano_change']()
        for var in self.grades.values():
            var.set.assert_called_once_with('')
        self.env['definir_texto_observacoes'].assert_called_once_with('')
        self.env['definir_texto_observacoes_gerais'].assert_called_once_with('')
        self.assertEqual(self.env['dados']['disciplinas_extra'], [])
        self.assertEqual(self.env['dados']['ano_sem_historico'], self.current)
        self.env['cursando_var'].set.assert_called_once_with(True)
        self.assertEqual(self.histories[self.previous]['nota_arte'], '9.5')
        self.env['aplicar_historico_por_ano'].assert_not_called()

    def test_selecting_past_year_restores_its_saved_history(self):
        self.env['ano_var'].get.return_value = self.previous
        self.env['on_ano_change']()
        self.env['aplicar_historico_por_ano'].assert_called_once_with(self.previous)
        self.env['definir_texto_observacoes'].assert_not_called()

    def test_programmatic_restore_does_not_clear_form(self):
        self.env['ano_var'].get.return_value = self.current
        self.env['bloqueio_auto']['ativo'] = True
        self.env['on_ano_change']()
        self.env['definir_texto_observacoes'].assert_not_called()
        self.env['aplicar_historico_por_ano'].assert_not_called()
