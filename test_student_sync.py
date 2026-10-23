import ast
import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import student_sync as sync

HEADERS = ['Matrícula', 'Nome do Aluno', 'Data Matrícula', 'Data Afastamento',
           'Data Nascimento do Aluno', 'Sexo do Aluno', 'Naturalidade',
           'Nome do Pai', 'Nome da Mãe', 'Situação do Aluno', 'Turma', 'Telefone Celular', 'Telefone Comercial',
           'Telefone Residencial', 'Telefone Respons\u00e1vel']
ROW = ['123456789', 'ALUNA TESTE', '10/08/2026', '', '01/01/2018', 'F',
       'CIDADE', 'PAI TESTE', 'MAE TESTE', 'ATIVO', 'TURMA TESTE',
       '(62) 09999-0000 / (62) 98888-0000', '', '(62) 3333-0000', '0062 97777-0000']

class StudentSyncTests(unittest.TestCase):
    def records(self):
        return sync.extrair_registros([[['RELATORIO']], [HEADERS, ROW, HEADERS, ROW]])

    def test_headers_repeated_and_duplicate_rows(self):
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['data_matricula'], '10/08/2026')
        self.assertEqual(records[0]['matricula'], '123456789')

    def test_phones_preserve_all_numbers_and_empty_fields(self):
        record = self.records()[0]
        self.assertEqual(record['telefone_celular'], ROW[-4])
        self.assertEqual(record['telefone_comercial'], '')
        self.assertEqual(record['telefone_residencial'], ROW[-2])
        self.assertEqual(record['telefone_responsavel'], ROW[-1])
        with tempfile.TemporaryDirectory() as directory:
            sync.salvar_base(directory, [record])
            for name in ('lista_alunos.csv', 'rel_aluno.csv'):
                with (Path(directory) / name).open(encoding='utf-8-sig', newline='') as file:
                    self.assertEqual(next(csv.DictReader(file, delimiter=';')), record)

    def test_old_daily_state_requires_refresh(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            sync.salvar_base(directory, self.records())
            path = Path(directory) / 'student_sync_state.json'
            state = json.loads(path.read_text())
            del state['campos']
            path.write_text(json.dumps(state))
            self.assertFalse(sync.base_atualizada_hoje(directory))

    def test_invalid_reports_rejected(self):
        for tables in ([], [[['Login'], ['Senha']]], [[HEADERS]], [[HEADERS[:-1], ROW[:-1]]]):
            with self.subTest(tables=tables), self.assertRaises(ValueError):
                sync.extrair_registros(tables)

    def test_old_report_identifies_missing_phone_columns(self):
        with self.assertRaises(ValueError) as error:
            sync.extrair_registros([[HEADERS[:-4], ROW[:-4]]])
        for field in ('telefone_celular', 'telefone_comercial', 'telefone_residencial', 'telefone_responsavel'):
            self.assertIn(field, str(error.exception))
        self.assertNotIn('ALUNA TESTE', str(error.exception))

    def test_abbreviated_report_phone_headers(self):
        for phones in (
            ['Celular', 'Comercial', 'Residencial', 'Respons\u00e1vel'],
            ['Tel. Celular', 'Tel. Comercial', 'Tel. Residencial', 'Tel. Respons\u00e1vel'],
            ['Fone Celular', 'Fone Comercial', 'Fone Residencial', 'Fone Responsavel'],
            ['Tel. Cel.', 'Tel. Com.', 'Tel. Resid.', 'Tel. Resp.'],
        ):
            with self.subTest(phones=phones):
                record = sync.extrair_registros([[HEADERS[:-4] + phones, ROW]])[0]
                self.assertEqual(record['telefone_celular'], ROW[-4])
                self.assertEqual(record['telefone_comercial'], '')
                self.assertEqual(record['telefone_residencial'], ROW[-2])
                self.assertEqual(record['telefone_responsavel'], ROW[-1])

    def test_reordered_abbreviated_phone_columns_keep_their_values(self):
        order = [14, 0, 12, 2, 1, 13, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        headers = HEADERS[:-4] + ['Celular', 'Comercial', 'Residencial', 'Responsavel']
        record = sync.extrair_registros([[[headers[i] for i in order], [ROW[i] for i in order]]])[0]
        self.assertEqual(record['telefone_responsavel'], ROW[-1])
        self.assertEqual(record['telefone_celular'], ROW[-4])

    def test_failure_logs_only_header_labels(self):
        from unittest.mock import patch
        headers = HEADERS[:-1] + ['Telefone desconhecido']
        with patch('builtins.print') as log, self.assertRaises(ValueError):
            sync.extrair_registros([[headers, ROW]])
        logged = ' '.join(str(item) for item in log.call_args_list)
        self.assertIn('Telefone desconhecido', logged)
        self.assertNotIn('ALUNA TESTE', logged)
        self.assertNotIn(ROW[-1], logged)

    def test_refresh_failure_logs_stage_and_closes_report(self):
        from unittest.mock import Mock
        page = Mock()
        page.is_closed.return_value = False
        report = page.context.new_page.return_value
        report.is_closed.return_value = False
        report.url = sync.REPORT_URL
        report.goto.side_effect = RuntimeError('teste de acesso')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sync, 'verificar_espaco'), patch('builtins.print') as log:
                with self.assertRaisesRegex(RuntimeError, 'teste de acesso'):
                    sync.atualizar_base_diaria(page, directory, forcar=True)
            logged = ' '.join(str(item) for item in log.call_args_list)
            self.assertIn('abrir formulario do relatorio', logged)
            self.assertIn('teste de acesso', logged)
            report.close.assert_called_once()
            self.assertFalse((Path(directory) / 'student_sync_state.json').exists())

    def test_save_backup_daily_state_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'lista_alunos.csv').write_bytes(b'previous')
            with patch.object(sync, 'hoje', return_value='2026-10-19'):
                sync.salvar_base(base, self.records())
                self.assertTrue(sync.base_atualizada_hoje(base))
                self.assertEqual(next((base / 'student_sync_backups').glob('*/lista_alunos.csv')).read_bytes(), b'previous')
                with patch.object(sync, 'hoje', return_value='2026-10-20'):
                    self.assertFalse(sync.base_atualizada_hoje(base))
                (base / 'rel_aluno.csv').write_bytes(b'changed')
                self.assertFalse(sync.base_atualizada_hoje(base))

    def test_second_replace_failure_restores_both_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ('lista_alunos.csv', 'rel_aluno.csv'):
                (base / name).write_bytes(name.encode())
            replace = sync.os.replace
            def failing(source, destination):
                if Path(destination).name == 'rel_aluno.csv':
                    raise PermissionError('file open')
                return replace(source, destination)
            with patch.object(sync.os, 'replace', side_effect=failing), self.assertRaises(PermissionError):
                sync.salvar_base(base, self.records())
            for name in ('lista_alunos.csv', 'rel_aluno.csv'):
                self.assertEqual((base / name).read_bytes(), name.encode())
            self.assertFalse((base / 'student_sync_state.json').exists())

    def test_low_disk_stops_before_browser_access(self):
        from unittest.mock import Mock
        page = Mock()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sync.shutil, 'disk_usage', return_value=type('Usage', (), {'free': 1024})()):
                with self.assertRaisesRegex(OSError, 'Espaco insuficiente'):
                    sync.atualizar_base_diaria(page, directory, forcar=True)
            page.context.new_page.assert_not_called()
            self.assertFalse((Path(directory) / 'student_sync_state.json').exists())

    def test_staging_failure_leaves_registers_unchanged(self):
        import errno
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ('lista_alunos.csv', 'rel_aluno.csv'):
                (base / name).write_bytes(name.encode())
            factory = sync.tempfile.NamedTemporaryFile
            calls = []
            def no_space(*args, **kwargs):
                calls.append(1)
                if len(calls) == 2:
                    raise OSError(errno.ENOSPC, 'No space left on device')
                return factory(*args, **kwargs)
            with patch.object(sync.tempfile, 'NamedTemporaryFile', side_effect=no_space):
                with self.assertRaises(OSError):
                    sync.salvar_base(base, self.records())
            for name in ('lista_alunos.csv', 'rel_aluno.csv'):
                self.assertEqual((base / name).read_bytes(), name.encode())
            self.assertEqual(list(base.glob('*.tmp')), [])
            self.assertFalse((base / 'student_sync_state.json').exists())

    def test_enrollment_period_and_class_reach_form(self):
        from datetime import datetime
        from typing import Any, List, Dict
        import re
        source = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        wanted = {'carregar_rel_aluno_csv', 'normalizar_serie', 'validar_data',
                  'aplicar_cadastro_matricula', 'on_transfer_date_change',
                  'serie_fundamental_1a5', 'calcular_carga_horaria'}
        nodes = [n for n in ast.walk(source)
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                 and n.name in wanted | {'CalendarioEscolar'}]
        import os
        env = dict(datetime=datetime, Any=Any, List=List, Dict=Dict, re=re, os=os,
                   csv=csv, normalizar_texto_busca=sync.normalizar, ORDINAL_INDICATOR=chr(186),
                   extrair_ano_4_digitos=lambda valor: str(valor))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<form>', 'exec'), env)
        class Var:
            def __init__(self, value=''): self.value = value
            def get(self): return self.value
            def set(self, value): self.value = value
        for name in ('nome_aluno', 'data_matricula', 'data_transferencia', 'ano',
                     'serie', 'cursando', 'carga_horaria', 'cidade', 'status_scan'):
            env[name + '_var'] = Var()
        env['nome_aluno_var'].set('ALUNA TESTE')
        record = dict(matricula='202654726', nome_aluno='ALUNA TESTE',
                      data_matricula='10/08/2026', data_afastamento='09/10/2026',
                      turma='EF301MA25 - 3\u00ba ANO A', situacao='TRANSFERIDO')
        env.update(carregar_base_rel_aluno=lambda: [record], bloqueio_auto={'ativo': False},
                   calendario_escolar=env['CalendarioEscolar']())
        self.assertTrue(env['aplicar_cadastro_matricula']('202654726'))
        self.assertEqual(env['ano_var'].get(), '2026')
        self.assertEqual(env['serie_var'].get(), '3\u00ba ANO')
        self.assertEqual(env['data_matricula_var'].get(), '10/08/2026')
        self.assertEqual(env['data_transferencia_var'].get(), '09/10/2026')
        self.assertEqual(env['carga_horaria_var'].get(), '790')
        for entrada in ('01/02/2026', '10/08/2026', 'data incompleta', ''):
            env['data_matricula_var'].set(entrada)
            env['on_transfer_date_change']()
            self.assertEqual(env['carga_horaria_var'].get(), '790')
        self.assertFalse(env['cursando_var'].get())
        cal = env['calendario_escolar']
        self.assertEqual(cal.calcular_dias_letivos('09/10/2026'), 158)
        self.assertEqual(cal.calcular_dias_letivos('18/01/2026'), 0)
        self.assertEqual(cal.calcular_dias_letivos('19/01/2026'), 1)
        totais = [10, 18, 22, 18, 19, 21, 1, 21, 21, 17, 19, 14]
        self.assertEqual([len(cal.dias_do_ano(2026)[f'{mes:02d}'])
                          for mes in range(1, 13)], totais)
        self.assertEqual(cal.calcular_dias_letivos('31/12/2026'), 201)
        self.assertEqual(cal.calcular_dias_letivos('30/06/2026'), 108)
        for mes, dias in cal.dias_do_ano(2026).items():
            self.assertEqual(len(dias), len(set(dias)))
            for dia in dias:
                datetime(2026, int(mes), dia)
        for data, incremento in [('07/02/2026', 1), ('13/06/2026', 1),
                                  ('31/07/2026', 1), ('04/12/2026', 1),
                                  ('07/09/2026', 0), ('12/10/2026', 0),
                                  ('02/10/2026', 1), ('18/12/2026', 1)]:
            from datetime import timedelta
            anterior = (datetime.strptime(data, '%d/%m/%Y') - timedelta(days=1)).strftime('%d/%m/%Y')
            self.assertEqual(cal.calcular_dias_letivos(data) - cal.calcular_dias_letivos(anterior), incremento)
        self.assertEqual(cal.calcular_dias_letivos('09/10/2024'), 155)
        with self.assertRaises(ValueError):
            cal.calcular_dias_letivos('09/10/2025')
        env['cidade_var'].set('APARECIDA DE GOIANIA')
        env['data_transferencia_var'].set('')
        env['on_transfer_date_change']()
        self.assertEqual(env['carga_horaria_var'].get(), '1005')
        env['serie_var'].set('AGRUPAMENTO 4')
        env['on_transfer_date_change']()
        self.assertEqual(env['carga_horaria_var'].get(), '804')
        env['data_transferencia_var'].set('09/10/2026')
        env['on_transfer_date_change']()
        self.assertEqual(env['carga_horaria_var'].get(), '632')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'students.csv'
            data = self.records()
            data[0]['data_afastamento'] = '09/10/2026'
            path.write_bytes(sync._csv_bytes(data))
            loaded = env['carregar_rel_aluno_csv'](str(path))[0]
            self.assertEqual(loaded['data_matricula'], '10/08/2026')
            self.assertEqual(loaded['data_afastamento'], '09/10/2026')
            self.assertEqual(loaded['turma'], 'TURMA TESTE')

    def test_csv_compatible_with_existing_readers(self):
        source = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        names = {'carregar_rel_aluno_csv', 'carregar_lista_alunos_por_nome'}
        nodes = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in names]
        import os, re
        from typing import List, Dict, Tuple
        env = dict(os=os, re=re, csv=csv, List=List, Dict=Dict, Tuple=Tuple,
                   normalizar_texto_busca=sync.normalizar)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<readers>', 'exec'), env)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'students.csv'
            path.write_bytes(sync._csv_bytes(self.records()))
            loaded = env['carregar_rel_aluno_csv'](str(path))[0]
            self.assertEqual(loaded['matricula'], '123456789')
            for field in ('telefone_celular', 'telefone_comercial', 'telefone_residencial', 'telefone_responsavel'):
                self.assertEqual(loaded[field], self.records()[0][field])
            self.assertEqual(env['carregar_lista_alunos_por_nome'](str(path))[0]['ALUNA TESTE'], ['123456789'])

if __name__ == '__main__':
    unittest.main()
