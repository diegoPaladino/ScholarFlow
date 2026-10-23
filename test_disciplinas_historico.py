from datetime import datetime
import json
from pathlib import Path
import re
import unittest
from urllib.parse import parse_qs

from playwright.sync_api import sync_playwright

import disciplinas_historico as disciplinas


class DisciplinasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.play = sync_playwright().start()
        cls.browser = cls.play.chromium.launch(headless=True)
        html = Path('HTML-GEMUL_POS_LANCAMENTO-DISCIPLINAS.txt').read_text(encoding='utf-8-sig')
        cls.template = re.search(r'<script[^>]*id="linhaTemplate"[^>]*>(.*?)</script>', html, re.S).group(1)
        cls.initial = re.search(r'<tbody id="tbodyDisciplinas">(.*?)</tbody>', html, re.S).group(1)
        cls.script = next(code for code in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
                          if 'function adicionarLinha()' in code)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.play.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.on('dialog', lambda d: d.accept())
        self.year = str(datetime.now().year)
        self.saved = []
        self.requests = []
        self.failure = False
        self.persist = True
        self.normalize_numbers = False
        self.wrong_grade = False
        self.page.route('**/*', self.serve)
        self.page.goto('https://gemul.test/disciplinas')

    def tearDown(self):
        self.page.close()

    def serve(self, route):
        if route.request.method == 'POST':
            data = {key: values[0] for key, values in parse_qs(route.request.post_data, keep_blank_values=True).items()}
            self.requests.append(data)
            if self.failure:
                route.fulfill(status=200, body='ERRO: falha ao salvar')
                return
            identity = str(9000000 + len(self.requests))
            if self.persist:
                self.saved = [row for row in self.saved if row['disciplina'] != data['disciplina']]
                persisted = dict(data, id=identity)
                if self.normalize_numbers and data['media']:
                    persisted['media'] = str(float(data['media'])).rstrip('0').rstrip('.')
                if self.wrong_grade and data['media']:
                    persisted['media'] = '1'
                self.saved.append(persisted)
            route.fulfill(status=200, body=identity)
            return
        rows = self.initial + ''.join(self.template.replace('data-id=""', f'data-id="{row["id"]}"') for row in self.saved)
        setup = """for (const data of SAVED) {
            const row = document.querySelector(`tr[data-id="${data.id}"]`);
            for (const [name,key] of [['cmbDisciplina','disciplina'], ['txtCH','ch'],
                ['cmbSituacaoPromocao','situacao'], ['txtMedia','media']])
                row.querySelector(`[name="${name}"]`).value = data[key];
        }""".replace('SAVED', json.dumps(self.saved))
        hidden = ''.join(f'<input name="{name}" value="{self.year if name == "txtAnoHistorico" else 1}">' for name in (
            'txtCodCurso', 'txtCodPeriodo', 'txtAnoHistorico', 'txtSemestreHistorico', 'codHistoricoEscolar'))
        content = (f'<form id="frm">{hidden}<table><tbody id="tbodyDisciplinas">{rows}</tbody></table>'
                   '<button type="button" onclick="adicionarLinha()">+ Nova Disciplina</button></form>'
                   f'<script type="text/template" id="linhaTemplate">{self.template}</script>'
                   f'<script>function validaMedia() {{}}; {self.script}</script><script>{setup}</script>')
        route.fulfill(status=200, content_type='text/html; charset=utf-8', body=content)

    def test_creates_missing_subjects_with_blank_hours_and_average_and_cursando(self):
        initial = disciplinas.registros(self.page)
        count = disciplinas.cadastrar(self.page, self.year)
        self.assertEqual(count, 9 - len(initial))
        self.assertEqual(len(self.requests), count)
        for request in self.requests:
            self.assertEqual(request['ch'], '')
            self.assertEqual(request['media'], '')
            self.assertEqual(request['situacao'], 'CR')
        rows = disciplinas.registros(self.page)
        self.assertEqual({disciplinas.normalizar(row['disciplina']) for row in rows},
                         {disciplinas.normalizar(name) for name in disciplinas.DISCIPLINAS})
        self.assertEqual(disciplinas.cadastrar(self.page, self.year), 0)
        self.assertEqual(len(self.requests), count)

    def test_numeric_grades_are_sent_and_confirmed_on_reload(self):
        self.initial = ''
        self.page.reload()
        notas = {'ARTES': '9.5', 'CIENCIAS': '8,0', 'MATEMATICA': '7.8'}
        self.assertEqual(disciplinas.cadastrar(self.page, self.year, notas=notas), 9)
        rows = {disciplinas.normalizar(row['disciplina']): row
                for row in disciplinas.registros(self.page)}
        for nome, nota in notas.items():
            self.assertEqual(rows[disciplinas.normalizar(nome)]['media'], nota.replace(',', '.'))
            self.assertFalse(rows[disciplinas.normalizar(nome)]['omitir'])
        disciplinas.cadastrar(self.page, self.year, notas={'ARTES': '8.7'})
        artes = next(row for row in disciplinas.registros(self.page) if row['disciplina'] == 'ARTES')
        self.assertEqual(artes['media'], '8.7')
        notas['ARTES'] = '8.7'
        before = len(self.requests)
        self.assertEqual(disciplinas.cadastrar(self.page, self.year, notas=notas), 0)
        self.assertEqual(len(self.requests), before)

    def test_normalized_grade_is_confirmed_without_resaving(self):
        self.initial = ''
        self.normalize_numbers = True
        self.page.reload()
        disciplinas.cadastrar(self.page, self.year, notas={'CIENCIAS': '8.0'})
        count = len(self.requests)
        disciplinas.cadastrar(self.page, self.year, notas={'CIENCIAS': '8,00'})
        self.assertEqual(len(self.requests), count)

    def test_genuinely_different_persisted_grade_still_fails(self):
        self.initial = ''
        self.wrong_grade = True
        self.page.reload()
        with self.assertRaisesRegex(RuntimeError, 'Nota divergente'):
            disciplinas.cadastrar(self.page, self.year, notas={'CIENCIAS': '8.0'})

    def test_extra_subject_from_catalog_is_saved_and_missing_is_reported(self):
        self.initial = ''
        self.page.reload()
        resumo = {}
        extras = [{'disciplina': 'Praticas de Leitura e Escrita', 'nota': '9.0'},
                  {'disciplina': 'Materia inexistente', 'nota': '8.5'}]
        self.assertEqual(disciplinas.cadastrar(self.page, self.year, extras=extras, resumo=resumo), 10)
        request = next(data for data in self.requests if data['disciplina'] == '10804')
        self.assertEqual(request['media'], '9.0')
        self.assertEqual(len(resumo['extras_lancadas']), 1)
        self.assertEqual(resumo['extras_ausentes'], [extras[1]])
        count = len(self.requests)
        disciplinas.cadastrar(self.page, self.year, extras=extras)
        self.assertEqual(len(self.requests), count)

    def test_missing_subjects_observation_preserves_text_and_is_idempotent(self):
        from html import escape
        stored = ['Observacao anterior. Disciplinas extras/complementares registradas neste ano: Estudos Matematicos (6,6).']
        general = ['Unidade e dados para conferencia.']
        writes = []
        def serve(route):
            path = route.request.url.rsplit('/', 1)[-1]
            if route.request.method == 'POST':
                data = parse_qs(route.request.post_data, keep_blank_values=True)
                stored[0] = data['txtObservacao'][0]
                general[0] = data['txtObservacaoGeral'][0]
                writes.append(stored[0])
                route.fulfill(status=200, content_type='text/html', body='Observacao salva.')
            elif path == 'edit':
                route.fulfill(content_type='text/html', body=
                    '<form method="post" action="/save"><textarea id="txtObservacao" name="txtObservacao">' +
                    escape(stored[0]) + '</textarea><textarea id="txtObservacaoGeral" name="txtObservacaoGeral">' +
                    escape(general[0]) + '</textarea><button>Salvar</button></form>')
            else:
                route.fulfill(content_type='text/html', body=
                    '<table><tr><td>2024</td><td><button onclick="location.href=&quot;/edit&quot;">Editar</button>'
                    '<button onclick="editarDisciplinas()">Editar Disciplinas</button></td></tr></table>')
        self.page.route('**/*', serve)
        for _ in range(2):
            disciplinas.acrescentar_observacao(self.page, 'https://gemul.test/list', '2024',
                '3 ANO', 'ESCOLA', 'Materia inexistente: 8.5.', lambda *args: 0,
                catalogo=['Estudos Matematicos'], limpar_geral=True)
        self.assertEqual(stored[0].replace('\r\n', '\n'), 'Observacao anterior.\nMateria inexistente: 8.5.')
        self.assertEqual(len(writes), 1)
        self.assertEqual(general[0], '')

    def test_server_error_stops_before_next_subject(self):
        self.failure = True
        with self.assertRaisesRegex(RuntimeError, 'não confirmou'):
            disciplinas.cadastrar(self.page, self.year)
        self.assertEqual(len(self.requests), 1)

    def test_past_year_uses_approved_and_keeps_hours_and_average_blank(self):
        self.year = '2022'
        self.initial = ''
        self.page.reload()
        self.assertEqual(disciplinas.cadastrar(self.page, self.year), 9)
        for request in self.requests:
            self.assertEqual(request['situacao'], 'AP')
            self.assertEqual(request['ch'], '')
            self.assertEqual(request['media'], '')

    def test_existing_past_cursando_warns_without_resending_saved_subjects(self):
        self.year = '2022'
        self.page.reload()
        before = disciplinas.registros(self.page)
        with self.assertRaisesRegex(RuntimeError, 'já contém disciplinas como Cursando'):
            disciplinas.cadastrar(self.page, self.year)
        self.assertEqual(self.requests, [])
        self.assertEqual(disciplinas.registros(self.page), before)

    def test_mismatched_page_year_blocks_all_writes(self):
        with self.assertRaisesRegex(RuntimeError, 'ano da página'):
            disciplinas.cadastrar(self.page, '2022')
        self.assertEqual(self.requests, [])

    def test_success_response_without_persistence_is_not_reported_as_success(self):
        self.persist = False
        with self.assertRaisesRegex(RuntimeError, 'não confirmada após recarregar'):
            disciplinas.cadastrar(self.page, self.year)


class SituacaoAnoTests(unittest.TestCase):
    def test_past_and_current_years(self):
        for year in (2022, 2023, 2024, 2025):
            self.assertEqual(disciplinas.situacao_por_ano(year, 2026), 'AP')
        self.assertEqual(disciplinas.situacao_por_ano('2026', 2026), 'CR')
        self.assertEqual(disciplinas.situacao_por_ano('2026', 2027), 'AP')

    def test_invalid_or_future_year_not_guessed(self):
        for year in ('', None, '22', '2026abc', 2027):
            with self.subTest(year=year), self.assertRaises(ValueError):
                disciplinas.situacao_por_ano(year, 2026)


if __name__ == '__main__':
    unittest.main()
