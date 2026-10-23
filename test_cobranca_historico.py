import ast
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import cobranca_historico as cobranca


class CobrancaTests(unittest.TestCase):
    def test_preview_replaced_for_each_student(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'textos.txt'
            cobranca.salvar_textos_padrao('Responsáveis SAMUEL', 'Instituição SAMUEL', path, registros=[{'telefone_celular': '(62) 97777-1111'}])
            cobranca.salvar_textos_padrao('Responsáveis YAGO', 'Instituição YAGO', path, registros=[{'telefone_celular': '(62) 99999-1234', 'telefone_responsavel': '+55 (62) 99999-1234', 'telefone_residencial': '(62) 3333-1234'}])
            text = path.read_text(encoding='utf-8-sig')
            self.assertIn('Responsáveis YAGO', text)
            self.assertIn('Instituição YAGO', text)
            self.assertNotIn('SAMUEL', text)
            self.assertNotIn('5562977771111', text)
            self.assertEqual(text.count('https://wa.me/5562999991234'), 1)
            self.assertIn('https://wa.me/556233331234', text)

    def test_preview_failed_replace_preserves_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'textos.txt'
            path.write_text('anterior', encoding='utf-8')
            with patch.object(cobranca.os, 'replace', side_effect=OSError('arquivo bloqueado')):
                with self.assertRaises(OSError):
                    cobranca.salvar_textos_padrao('novo', 'novo', path)
            self.assertEqual(path.read_text(encoding='utf-8'), 'anterior')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_multiple_numbers_country_code_duplicates_and_sources(self):
        contatos = cobranca.contatos([{
            'telefone_celular': '(62) 99999-1234 / +55 (62) 98888-4321',
            'telefone_responsavel': '5562999991234',
            'telefone_comercial': '(62) 3333-1234',
            'telefone_residencial': 'sem telefone',
        }])
        self.assertEqual([c['numero'] for c in contatos],
                         ['5562999991234', '5562988884321', '556233331234'])
        self.assertEqual(len(contatos[0]['origens']), 2)

    def test_missing_ddd_invalid_numbers_and_ddd_55(self):
        self.assertEqual(cobranca.contatos([{'telefone_celular': '99999-1234 / (00) 99999-1234 / 1234567890123456'}]), [])
        self.assertEqual(cobranca.contatos([{'telefone_celular': '(55) 99999-1234'}])[0]['numero'],
                         '5555999991234')

    def test_handoff_order_and_final_clipboard(self):
        events = Mock()
        cobranca.abrir_conversa('5562999991234', 'texto da cobrança', {'x': -10, 'y': 20},
                               events.mouse, events.clipboard)
        self.assertEqual(events.mock_calls, [
            call.mouse.click(-10, 20), call.mouse.sleep(0.4),
            call.mouse.hotkey('ctrl', 't'), call.mouse.sleep(0.4),
            call.clipboard.copy('https://wa.me/5562999991234'),
            call.mouse.hotkey('ctrl', 'v'), call.mouse.sleep(0.2),
            call.mouse.press('enter'), call.clipboard.copy('texto da cobrança')])

    def test_failure_restores_message_to_clipboard(self):
        mouse, clipboard = Mock(), Mock()
        mouse.hotkey.side_effect = RuntimeError('falha')
        with self.assertRaises(RuntimeError):
            cobranca.abrir_conversa('5562999991234', 'mensagem', {'x': 1, 'y': 2}, mouse, clipboard)
        clipboard.copy.assert_called_with('mensagem')

    def test_used_contacts_persist_per_student(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cobranca.carregar_utilizados(directory, '123456789'), set())
            cobranca.marcar_utilizado(directory, '123456789', '5562999991234')
            cobranca.marcar_utilizado(directory, '123456789', '5562999991234')
            self.assertEqual(cobranca.carregar_utilizados(directory, '123456789'), {'5562999991234'})
            self.assertEqual(cobranca.carregar_utilizados(directory, '987654321'), set())

    def institutional_template(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'gerar_texto_cobranca_institucional')
        env = {'re': re, 'ESCOLA_PADRAO': 'ESCOLA MUNICIPAL JARDIM BELA VISTA'}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<institutional-template>', 'exec'), env)
        return env['gerar_texto_cobranca_institucional']

    def test_institutional_request_identifies_student_and_return_email(self):
        text = self.institutional_template()({
            'nome_aluno': 'ALUNA TESTE', 'numero_matricula': '123456789',
            'data_nascimento': '10/03/2015', 'nome_escola': 'OUTRA ESCOLA'})
        self.assertTrue(text.startswith('Assunto:'))
        for value in ('ALUNA TESTE', '10/03/2015', 'histórico escolar escaneado',
                      'escolamjardimbelavista@gmail.com', 'ESCOLA MUNICIPAL JARDIM BELA VISTA'):
            self.assertIn(value, text)
        self.assertNotIn('OUTRA ESCOLA', text)
        self.assertNotIn('123456789', text)

    def test_institutional_request_omits_missing_birthdate_and_validates_student(self):
        generate = self.institutional_template()
        text = generate({'nome_aluno': 'ALUNA TESTE', 'numero_matricula': '123456789'})
        self.assertNotIn('data de nascimento:', text)
        self.assertNotIn('None', text)
        for data in ({}, {'nome_aluno': 'ALUNA', 'numero_matricula': '123'},
                     {'nome_aluno': '', 'numero_matricula': '123456789'}):
            with self.assertRaises(ValueError):
                generate(data)

    def test_exact_template_uses_requesting_school(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'gerar_texto_cobranca_historico')
        school = 'ESCOLA MUNICIPAL JARDIM BELA VISTA'
        env = {'re': re, 'ESCOLA_PADRAO': school}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<template>', 'exec'), env)
        text = env['gerar_texto_cobranca_historico']({
            'nome_aluno': 'ALUNA TESTE', 'numero_matricula': '123456789', 'nome_escola': 'ESCOLA ANTERIOR'})
        self.assertEqual(text, f'Olá! Aqui é da secretaria da {school}.\n\n'
            'Falta entregar o histórico escolar de ALUNA TESTE (matrícula 123456789).\n\n'
            f'Peça esse documento na escola anterior e entregue na secretaria da {school}.\n\nObrigado!')


if __name__ == '__main__':
    unittest.main()
