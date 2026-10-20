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
               'sessao_execucao': {'historico_alvo': {}},
               'registrar_etapa_historico': Mock(), 'abrir_disciplinas_registro': Mock()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<navigation>', 'exec'), env)
        page = Mock(url='https://example.test/app/sca_historico_escolar_novo.asp')
        discipline = page.locator.return_value
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
        parser.feed(Path('HTML-GEMUL_POS_LANCAMENTO.txt').read_text(encoding='utf-8-sig'))
        matching = [row for row in parser.rows if len(row) >= 5 and row[0] == '2026']
        self.assertTrue(any(row[2] == 'ESCOLA MUNICIPAL JARDIM BELA VISTA' and '3' in row[4] for row in matching))

    def test_initial_form_saved_before_waiting_for_disciplines(self):
        page, discipline, button = self.transition()
        button.scroll_into_view_if_needed.assert_called_once()
        button.click.assert_called_once()
        discipline.wait_for.assert_called_once_with(state='visible', timeout=15000)

    def test_existing_disciplines_do_not_submit_again(self):
        page, discipline, button = self.transition(present=True)
        button.click.assert_not_called()

    def test_page_down_fallback(self):
        page, discipline, button = self.transition(scroll_error=True)
        page.keyboard.press.assert_called_with('PageDown')
        button.click.assert_called_once()

if __name__ == '__main__':
    unittest.main()
