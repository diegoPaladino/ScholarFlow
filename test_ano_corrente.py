import ast
import re
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
import student_sync


class AnoCorrenteTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        names = {'normalizar_serie', 'aplicar_escola_serie_ano_corrente'}
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names]
        self.interp = tk.Tcl()
        self.records = [{'matricula': '202600001', 'turma': '3 ANO A',
                         'data_matricula': '01/02/' + str(datetime.now().year)}]
        self.env = dict(re=re, datetime=datetime, ESCOLA_PADRAO='ESCOLA MUNICIPAL JARDIM BELA VISTA',
                        ORDINAL_INDICATOR=chr(186), normalizar_texto_busca=student_sync.normalizar,
                        bloqueio_auto={'ativo': False}, carregar_base_rel_aluno=lambda: self.records,
                        aplicar_dados_escola_padrao=Mock(), on_transfer_date_change=Mock(),
                        extrair_ano_4_digitos=lambda value: value,
                        validar_data=lambda value: bool(re.fullmatch(r'\d{2}/\d{2}/\d{4}', value)))
        for key, value in {'ano_var': str(datetime.now().year), 'numero_matricula_var': '202600001',
                           'nome_escola_var': 'ESCOLA ANTERIOR', 'serie_var': '4º ANO',
                           'status_scan_var': ''}.items():
            self.env[key] = tk.StringVar(master=self.interp, value=value)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<current-year>', 'exec'), self.env)

    def apply(self):
        self.env['aplicar_escola_serie_ano_corrente']()

    def test_current_year_uses_school_and_registered_class(self):
        self.apply()
        self.assertEqual(self.env['nome_escola_var'].get(), self.env['ESCOLA_PADRAO'])
        self.assertEqual(self.env['serie_var'].get(), '3º ANO')
        self.env['aplicar_dados_escola_padrao'].assert_called_once()

    def test_previous_year_preserves_history(self):
        self.env['ano_var'].set(str(datetime.now().year - 1))
        self.apply()
        self.assertEqual(self.env['nome_escola_var'].get(), 'ESCOLA ANTERIOR')
        self.assertEqual(self.env['serie_var'].get(), '4º ANO')

    def test_internal_transfer_with_roman_group(self):
        self.records = [{'matricula': '202600001',
                         'turma': 'EI502VA25 - AGRUPAMENTO V C',
                         'situacao': 'TRANSFERÊNCIA INTERNA',
                         'data_matricula': '10/08/' + str(datetime.now().year),
                         'data_afastamento': '01/10/' + str(datetime.now().year)}]
        self.apply()
        self.assertEqual(self.env['serie_var'].get(), 'AGRUPAMENTO 5')

    def test_roman_groups_use_whole_tokens(self):
        normalize = self.env['normalizar_serie']
        self.assertEqual(normalize('AGRUPAMENTO IV A'), 'AGRUPAMENTO 4')
        self.assertEqual(normalize('AGRUPAMENTO V C'), 'AGRUPAMENTO 5')
        self.assertEqual(normalize('AGRUPAMENTO VI A'), '')
        self.assertEqual(normalize('AGRUPAMENTO 50'), '')

    def test_missing_or_conflicting_registration_clears_stale_class(self):
        for records in ([], self.records + [{'matricula': '202600001', 'turma': '2 ANO'}]):
            self.records = records
            self.env['serie_var'].set('4º ANO')
            self.apply()
            self.assertEqual(self.env['serie_var'].get(), '')
            self.assertTrue(self.env['status_scan_var'].get())

    def test_old_enrollment_is_ignored(self):
        self.records.append({'matricula': '202600001', 'turma': '2 ANO',
                             'data_afastamento': '01/12/' + str(datetime.now().year - 1)})
        self.apply()
        self.assertEqual(self.env['serie_var'].get(), '3º ANO')

    def test_reapplication_does_not_write_unchanged_values(self):
        self.apply()
        writes = Mock()
        for key in ('nome_escola_var', 'serie_var'):
            self.env[key].trace_add('write', writes)
        self.apply()
        writes.assert_not_called()
