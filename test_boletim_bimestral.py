from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs

from playwright.sync_api import sync_playwright

import boletim_bimestral as boletim


class ReportCardTests(unittest.TestCase):
    def setUp(self):
        self.matricula = '202600001'
        self.data = dict(numero_matricula=self.matricula, nome_aluno='ALUNA TESTE',
                         ano='2026', turma='1 ANO A', notas=[
                             dict(disciplina='ARTES', bimestre='1', nota='0'),
                             dict(disciplina='ARTES', bimestre='2', nota='8,5')])

    def test_zero_and_decimal_comma_are_preserved(self):
        result = boletim.validar(self.data, self.matricula)
        self.assertEqual([n['nota'] for n in result['notas']], ['0', '8.5'])
        self.assertEqual(result['notas'][0]['bimestre'], '1')

    def test_wrong_student_and_invalid_fields_are_rejected(self):
        for change in ({'ano': ''}, {'notas': []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                boletim.validar(dict(self.data, **change), self.matricula)
        for grade in ('11', '-1', 'NaN', 'Infinity', 'A'):
            data = deepcopy(self.data)
            data['notas'][0]['nota'] = grade
            with self.subTest(grade=grade), self.assertRaises(ValueError):
                boletim.validar(data, self.matricula)

    def test_source_school_registration_differs_without_changing_gemul_registration(self):
        self.data['numero_matricula'] = '90000000001'
        result = boletim.validar(self.data, self.matricula, 'ALUNA TESTE')
        self.assertEqual(result['numero_matricula'], self.matricula)
        self.assertEqual(result['numero_matricula_origem'], '90000000001')
        with tempfile.TemporaryDirectory() as directory:
            boletim.salvar(directory, self.matricula, result, ['boletim.png'])
            cached = boletim.carregar(directory, self.matricula)['boletins']['2026']
            self.assertEqual(cached['numero_matricula_origem'], '90000000001')
            self.assertEqual(cached['numero_matricula'], self.matricula)

    def test_normalized_cache_cannot_be_rebound_to_another_gemul_student(self):
        result = boletim.validar(self.data, self.matricula)
        with self.assertRaisesRegex(ValueError, 'vinculado a outra matrícula'):
            boletim.validar(result, '202600002')

    def test_ficha_individual_model_keeps_only_exact_standard_subjects_and_filled_quarters(self):
        componentes = [
            ('ARTE', '8,0', '9,0'), ('CIÊNCIAS', '7,0', '7,5'), ('EDUCAÇÃO FÍSICA', '9,5', '9,5'),
            ('GEOGRAFIA', '7,0', '7,5'), ('HISTÓRIA', '7,0', '7,5'), ('LÍNGUA INGLESA', '7,0', '7,0'),
            ('LÍNGUA PORTUGUESA', '7,0', '7,0'), ('MATEMÁTICA', '7,0', '7,0'),
            ('LEITURA E FLUÊNCIA', '7,0', '7,0'), ('MATEMÁTICA LÚDICA', '7,0', '7,0'),
            ('COMPUTAÇÃO', '-', '-'),
        ]
        self.data['notas'] = [dict(disciplina=d, bimestre=str(b), nota=nota)
                              for d, primeiro, segundo in componentes
                              for b, nota in [(1, primeiro), (2, segundo), (3, ''), (4, '-')]]
        result = boletim.validar(self.data, self.matricula)
        self.assertEqual(len(result['notas']), 14)
        self.assertEqual({n['bimestre'] for n in result['notas']}, {'1', '2'})
        self.assertEqual(result['notas'][0]['disciplina'], 'ARTES')
        self.assertEqual(len(result['disciplinas_ignoradas']), 4)
        self.assertNotIn('MATEMÁTICA LÚDICA', {n['disciplina'] for n in result['notas']})

    def test_unsupported_subject_does_not_block_even_with_non_numeric_concept(self):
        self.data['notas'].append(dict(disciplina='LÍNGUA INGLESA', bimestre='1', nota='A'))
        result = boletim.validar(self.data, self.matricula)
        self.assertEqual(len(result['notas']), 2)
        self.assertIn('LÍNGUA INGLESA', result['disciplinas_ignoradas'])

    def test_name_mismatch_is_not_associated_with_selected_student(self):
        with self.assertRaisesRegex(ValueError, 'nome do boletim'):
            boletim.validar(self.data, self.matricula, 'OUTRO ESTUDANTE')

    def test_conflicting_duplicate_is_not_silently_overwritten(self):
        self.data['notas'].append(dict(disciplina='ARTES', bimestre='1', nota='9'))
        with self.assertRaisesRegex(ValueError, 'conflitantes'):
            boletim.validar(self.data, self.matricula)

    def test_cache_is_per_student_and_preserves_previous_year(self):
        with tempfile.TemporaryDirectory() as directory:
            boletim.salvar(directory, self.matricula, self.data, ['boletim.png'])
            boletim.salvar(directory, self.matricula, dict(self.data, ano='2025'), ['anterior.png'])
            payload = boletim.carregar(directory, self.matricula)
            self.assertEqual(set(payload['boletins']), {'2025', '2026'})
            self.assertEqual(payload['boletins']['2026']['notas'][0]['nota'], '0')
            self.assertIsNone(boletim.carregar(directory, '202600002'))


class FilterNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.play.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.posts = []
        self.year = str(datetime.now().year)
        self.fields = {'txtAnoLetivo': self.year, 'cmbSemestre': '3', 'cmbTurma': '0', 'cmbDisciplinaTurma': '0', 'cmbativos': 'A'}

        def serve(route):
            if route.request.method == 'POST':
                data = {k: v[0] for k, v in parse_qs(route.request.post_data).items()}
                self.posts.append(data)
                self.fields.update(data)
            selects = ''
            for name, value, label in [('cmbSemestre', '3', 'Anual'), ('cmbTurma', '7', '1 ANO A'),
                                       ('cmbDisciplinaTurma', '9', 'ARTES'), ('cmbativos', 'T', 'Todas as Situações')]:
                selected = 'selected' if self.fields[name] == value else ''
                selects += (f'<select id="{name}" name="{name}" onchange="this.form.submit()">'
                            f'<option value="0">Selecione</option><option value="{value}" {selected}>{label}</option></select>')
            route.fulfill(content_type='text/html; charset=utf-8', body='<form method="post">' +
                f'<input id="txtAnoLetivo" name="txtAnoLetivo" value="{self.fields["txtAnoLetivo"]}" onblur="this.form.submit()">' +
                selects + '</form>')
        self.page.route('**/*', serve)

    def tearDown(self):
        self.page.close()

    def test_filters_navigate_without_submitting_any_student_or_grade(self):
        result = boletim.preparar_tela(self.page, 'https://gemul.test', {'ano': self.year}, '1 ANO A', 'ARTES')
        self.assertEqual(self.fields['txtAnoLetivo'], self.year)
        self.assertEqual(self.fields['cmbDisciplinaTurma'], '9')
        self.assertIn('Nenhuma nota foi gravada', result)
        self.assertTrue(all(set(post) <= set(self.fields) for post in self.posts))
        self.assertEqual(len(self.posts), 3)

    def test_unknown_class_stops_before_any_grade_or_student_selection(self):
        with self.assertRaisesRegex(RuntimeError, 'Opção não encontrada'):
            boletim.preparar_tela(self.page, 'https://gemul.test', {'ano': self.year}, 'TURMA INEXISTENTE', 'ARTES')
        self.assertEqual(self.posts, [])

    def test_old_report_card_never_opens_current_year_launch(self):
        page = Mock()
        with self.assertRaisesRegex(ValueError, 'ano corrente'):
            boletim.preparar_tela(page, 'https://gemul.test', {'ano': str(int(self.year) - 1)}, '1 ANO A', 'ARTES')
        page.goto.assert_not_called()


class GradeSubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(headless=True)
        capture = Path('HTML-GEMUL_POS_LANCAMENTO-NOTAS-BIMESTRAIS-2.txt').read_text(encoding='utf-8-sig')
        start = capture.index('<form id="frm"')
        cls.form = capture[start:capture.index('<!-- this overlay', start)]
        cls.grade_script = next(s for s in re.findall(r'<script[^>]*>(.*?)</script>', capture, re.S)
                                if 'function salvar(acao)' in s)
        filters = Path('HTML-GEMUL_POS_LANCAMENTO-NOTAS-BIMESTRAIS.txt').read_text(encoding='utf-8-sig')
        cls.filter_script = next(s for s in re.findall(r'<script[^>]*>(.*?)</script>', filters, re.S)
                                 if 'function cadastrarNotas()' in s)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.play.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.on('dialog', lambda dialog: dialog.accept())
        self.year = str(datetime.now().year)
        self.data = dict(numero_matricula='202600001', nome_aluno='ALUNA TESTE', ano=self.year,
                         turma='1 ANO A', notas=[
                             dict(disciplina='ARTES', bimestre='1', nota='0'),
                             dict(disciplina='ARTES', bimestre='2', nota='8,5'),
                             dict(disciplina='CIÊNCIAS', bimestre='2', nota='9')])
        self.turma = 'EF101MA25 - 1º ANO A'
        self.fields = {'txtAnoLetivo': self.year, 'cmbSemestre': '3', 'cmbTurma': '0',
                       'cmbDisciplinaTurma': '0', 'cmbativos': 'A'}
        self.saved = {disciplina: {'00': '', '01': '', '02': '7', '03': '', '05': '3', '07': '4'}
                      for disciplina in ('695', '750')}
        self.writes, self.selections = [], []
        self.no_persist = set()
        self.wrong_student = False
        self.duplicate_student = False
        self.missing_science = False
        self.page.route('**/*', self.serve)

    def tearDown(self):
        self.page.close()

    def serve(self, route):
        path = route.request.url.split('?')[0].rsplit('/', 1)[-1]
        data = {k: v[0] for k, v in parse_qs(route.request.post_data or '', keep_blank_values=True).items()}
        if path == 'sca_lancamento_notas_cod.asp':
            self.writes.append(data)
            disciplina = data['cmbDisciplinaTurma']
            if disciplina not in self.no_persist:
                for sufixo in self.saved[disciplina]:
                    self.saved[disciplina][sufixo] = data[f'txtNota_1_{sufixo}']
            route.fulfill(status=200, content_type='text/html', body='Salvo!')
            return
        if path == 'sca_lancamento_notas.asp':
            self.selections.append(parse_qs(route.request.post_data).get('chkAluno', []))
            disciplina = data['cmbDisciplinaTurma']
            matricula = '202600002' if self.wrong_student else '202600001'
            setup = '''
                const row = document.querySelector('input[name="txtCodAluno_1"]').closest('tr');
                row.cells[1].firstChild.textContent = DATA.matricula;
                row.cells[2].textContent = 'ALUNA TESTE';
                row.querySelector('input[name="txtCodAluno_1"]').value = '101';
                document.querySelector('[name="chkAluno"]').value = '101';
                document.querySelector('[name="cmbTurma"]').value = '7';
                document.querySelector('#txtAnoLetivo').value = DATA.year;
                document.querySelector('#cmbDisciplinaTurma').value = DATA.disciplina;
                for (const [suffix, grade] of Object.entries(DATA.notas))
                    row.querySelector(`[name="txtNota_1_${suffix}"]`).value = grade;
            '''.replace('DATA', json.dumps(dict(matricula=matricula, year=self.year,
                                               disciplina=disciplina, notas=self.saved[disciplina])))
            route.fulfill(content_type='text/html; charset=utf-8', body=self.form +
                          '<script>' + self.grade_script + '</script><script>' + setup + '</script>')
            return
        if route.request.method == 'POST':
            self.fields.update({k: v for k, v in data.items() if k in self.fields})
        else:
            self.fields.update(cmbTurma='0', cmbDisciplinaTurma='0', cmbativos='A')
        selects = ''
        options = {
            'cmbSemestre': [('3', 'Anual')], 'cmbTurma': [('7', self.turma)],
            'cmbDisciplinaTurma': [('695', 'ARTES')] + ([] if self.missing_science else [('750', 'CIÊNCIAS')]),
            'cmbativos': [('A', 'Somente Ativos'), ('T', 'Todas as Situações')],
        }
        for name, opcoes in options.items():
            selects += f'<select id="{name}" name="{name}" onchange="this.form.submit()"><option value="0">Selecione</option>'
            for value, label in opcoes:
                selected = 'selected' if self.fields[name] == value else ''
                selects += f'<option value="{value}" {selected}>{label}</option>'
            selects += '</select>'
        # Another student starts selected: the automation must explicitly deselect them.
        rows = '<tr><td><input type="checkbox" name="chkAluno" value="102" checked></td><td>1</td><td>202600002</td><td>OUTRO ALUNO</td></tr>'
        if self.fields['cmbativos'] == 'T':
            alvo = '<tr><td><input type="checkbox" name="chkAluno" value="101"></td><td>2</td><td>202600001</td><td>ALUNA TESTE</td><td>TRANSFERIDO</td></tr>'
            rows += alvo * (2 if self.duplicate_student else 1)
        route.fulfill(content_type='text/html; charset=utf-8', body='<form id="frm" method="post">' +
            f'<input id="txtAnoLetivo" name="txtAnoLetivo" value="{self.year}" onblur="this.form.submit()">' +
            selects + '<table>' + rows + '</table><button type="button" id="cmbCadastrar" onclick="cadastrarNotas()">Cadastrar</button></form>' +
            '<script>' + self.filter_script + '</script>')

    def launch(self):
        return boletim.lancar(self.page, 'https://gemul.test', self.data, self.turma, timeout_ms=4000)

    def test_transferred_student_all_subjects_preserve_untouched_grades_and_are_idempotent(self):
        result = self.launch()
        self.assertEqual(result['notas'], 3)
        self.assertEqual(len(self.writes), 2)
        self.assertTrue(all(post['chkAluno'] == '101' and post['qtdeAluno'] == '1'
                            and post['cmbTurma'] == '7' for post in self.writes))
        self.assertTrue(all(ids == ['101'] for ids in self.selections))
        self.assertEqual(self.saved['695']['00'], '0')
        self.assertEqual(self.saved['695']['01'], '8,5')
        for disciplina in ('695', '750'):
            self.assertEqual(self.saved[disciplina]['02'], '7')
            self.assertEqual(self.saved[disciplina]['05'], '3')
            self.assertEqual(self.saved[disciplina]['07'], '4')
        self.launch()
        self.assertEqual(len(self.writes), 2)

    def test_wrong_student_in_grade_form_blocks_all_grade_writes(self):
        self.wrong_student = True
        with self.assertRaisesRegex(boletim.LancamentoIncompleto, 'matrícula na página'):
            self.launch()
        self.assertEqual(self.writes, [])

    def test_duplicate_matricula_never_opens_grade_form(self):
        self.duplicate_student = True
        with self.assertRaisesRegex(boletim.LancamentoIncompleto, 'não encontrada de forma única'):
            self.launch()
        self.assertEqual(self.writes, [])
        self.assertEqual(self.selections, [])

    def test_success_response_without_persistence_is_not_reported_as_success(self):
        self.no_persist = {'695'}
        with self.assertRaisesRegex(boletim.LancamentoIncompleto, 'não confirmada após reabrir'):
            self.launch()

    def test_failure_on_second_subject_reports_previously_confirmed_subject(self):
        self.no_persist = {'750'}
        with self.assertRaisesRegex(boletim.LancamentoIncompleto, 'Disciplinas confirmadas: ARTES'):
            self.launch()
        self.assertEqual(self.saved['695']['01'], '8,5')

    def test_missing_subject_never_writes_to_a_different_subject(self):
        self.missing_science = True
        result = self.launch()
        self.assertEqual(result['notas'], 2)
        self.assertEqual(result['ignoradas'], ['CIÊNCIAS'])
        self.assertEqual([p['cmbDisciplinaTurma'] for p in self.writes], ['695'])

    def test_subjects_outside_standard_never_open_gemul_or_write_observations(self):
        self.data['notas'].append(dict(disciplina='MATEMÁTICA LÚDICA', bimestre='1', nota='7'))
        result = self.launch()
        self.assertEqual(result['notas'], 3)
        self.assertEqual(result['ignoradas'], ['MATEMÁTICA LÚDICA'])
        self.assertEqual(len(self.writes), 2)


class ClassLookupTests(unittest.TestCase):
    def test_class_comes_from_selected_student_register(self):
        rows = [dict(matricula='202600001', turma='EF101MA25 - 1º ANO A'),
                dict(matricula='202600002', turma='OUTRA TURMA')]
        self.assertEqual(boletim.turma_do_cadastro(rows, '202600001', 'TURMA DO DOCUMENTO'), rows[0]['turma'])

    def test_ambiguous_class_is_rejected(self):
        rows = [dict(matricula='202600001', turma='TURMA A'), dict(matricula='202600001', turma='TURMA B')]
        with self.assertRaises(ValueError):
            boletim.turma_do_cadastro(rows, '202600001')
