import ast
from pathlib import Path
import re
import unittest
from unittest.mock import Mock

import student_transfer as transfer


class StudentTransferTests(unittest.TestCase):
    def record(self, situacao, matricula='123456789', nome='ALUNO TESTE'):
        return dict(matricula=matricula, nome_aluno=nome, situacao=situacao)

    def test_transferred_requires_matching_student_and_all_enrollments(self):
        self.assertTrue(transfer.esta_transferido([self.record(' transferido ')], '123456789', 'aluno teste'))
        for records in ([], [self.record('ATIVO')], [self.record('')],
                        [self.record('TRANSFERIDO'), self.record('ATIVO')],
                        [self.record('TRANSFERIDO', matricula='999999999')],
                        [self.record('TRANSFERIDO', nome='OUTRO ALUNO')]):
            with self.subTest(records=records):
                self.assertFalse(transfer.esta_transferido(records, '123456789', 'ALUNO TESTE'))

    def test_only_active_requires_confirmation(self):
        for status in ('TRANSFERENCIA INTERNA', 'CANCELADO', 'DESISTENTE', 'FALECIDO', 'TRANSFERIDO', ''):
            transfer.exigir_transferido([self.record(status)], '123456789', 'ALUNO TESTE')
        records = [self.record('TRANSFERIDO'), self.record(' ativo ')]
        with self.assertRaisesRegex(ValueError, 'ATIVO'):
            transfer.exigir_transferido(records, '123456789', 'ALUNO TESTE')
        transfer.exigir_transferido(records, '123456789', 'ALUNO TESTE', permitir_ativo=True)

    def test_manual_page_uses_authenticated_context_without_changing_student(self):
        page = Mock()
        manual = transfer.abrir_pagina(page)
        self.assertIs(manual, page.context.new_page.return_value)
        manual.goto.assert_called_once_with(transfer.TRANSFER_URL, wait_until='domcontentloaded', timeout=60000)
        manual.bring_to_front.assert_called_once()
        manual.locator.assert_not_called()
        page.goto.assert_not_called()

    def test_failed_page_open_cleans_up(self):
        page = Mock()
        manual = page.context.new_page.return_value
        manual.goto.side_effect = RuntimeError('falha')
        with self.assertRaisesRegex(RuntimeError, 'falha'):
            transfer.abrir_pagina(page)
        manual.close.assert_called_once()

    def dialog(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == 'garantir_aluno_transferido')
        registro = self.record('ATIVO')
        buttons = {}
        tk, ttk, root = Mock(), Mock(), Mock()
        window = tk.Toplevel.return_value
        window.winfo_exists.return_value = True
        window.destroy.side_effect = lambda: setattr(window.winfo_exists, 'return_value', False)
        def make_button(*args, **kwargs):
            buttons[kwargs['text']] = kwargs['command']
            return Mock()
        ttk.Button.side_effect = make_button
        env = dict(re=re, student_transfer=transfer, tk=tk, ttk=ttk, root=root,
                   conferencia_transferencia={'ativa': False, 'pagina': None},
                   numero_matricula_var=Mock(get=lambda: '123456789'),
                   nome_aluno_var=Mock(get=lambda: 'ALUNO TESTE'),
                   carregar_base_rel_aluno=lambda: [registro],
                   messagebox=Mock(askyesnocancel=Mock(return_value=False)), traceback=Mock(), garantir_sessao_gemul=Mock(),
                   _get_base=lambda page: page, registrar_etapa_historico=Mock(),
                   status_scan_var=Mock(), cursando_var=Mock(),
                   atualizar_base_alunos=Mock(return_value=True))
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<transfer-dialog>', 'exec'), env)
        return env, registro, buttons, root, window

    def test_active_can_continue_without_opening_browser(self):
        env, registro, buttons, root, window = self.dialog()
        env['messagebox'].askyesnocancel.return_value = True
        self.assertTrue(env['garantir_aluno_transferido']())
        env['garantir_sessao_gemul'].assert_not_called()
        self.assertEqual(env['conferencia_transferencia']['aluno_confirmado'], ('123456789', 'ALUNO TESTE'))

    def test_active_can_cancel_before_browser(self):
        env, registro, buttons, root, window = self.dialog()
        env['messagebox'].askyesnocancel.return_value = None
        self.assertFalse(env['garantir_aluno_transferido']())
        env['garantir_sessao_gemul'].assert_not_called()

    def test_other_statuses_proceed_without_dialog(self):
        for status in ('TRANSFERENCIA INTERNA', 'CANCELADO', 'DESISTENTE', 'FALECIDO', 'TRANSFERIDO'):
            env, registro, buttons, root, window = self.dialog()
            registro['situacao'] = status
            self.assertTrue(env['garantir_aluno_transferido']())
            env['messagebox'].askyesnocancel.assert_not_called()

    def test_continue_from_review_while_still_active(self):
        env, registro, buttons, root, window = self.dialog()
        root.wait_window.side_effect = lambda _: buttons['Continuar mesmo assim']()
        self.assertTrue(env['garantir_aluno_transferido']())
        self.assertEqual(registro['situacao'], 'ATIVO')

    def test_dialog_waits_for_fresh_confirmation(self):
        env, registro, buttons, root, window = self.dialog()
        def wait(_window):
            buttons['Conferir novamente']()
            window.destroy.assert_not_called()
            registro['situacao'] = 'TRANSFERIDO'
            buttons['Conferir novamente']()
        root.wait_window.side_effect = wait
        self.assertTrue(env['garantir_aluno_transferido']())
        self.assertEqual(env['atualizar_base_alunos'].call_count, 2)
        env['atualizar_base_alunos'].assert_called_with(forcar=True)
        env['cursando_var'].set.assert_called_once_with(False)

    def test_dialog_cancel_or_failed_refresh_does_not_release(self):
        for fail_refresh in (False, True):
            env, registro, buttons, root, window = self.dialog()
            def wait(_window):
                if fail_refresh:
                    env['atualizar_base_alunos'].return_value = False
                    registro['situacao'] = 'TRANSFERIDO'
                    buttons['Conferir novamente']()
                    window.destroy.assert_not_called()
                buttons['Cancelar']()
            root.wait_window.side_effect = wait
            self.assertFalse(env['garantir_aluno_transferido']())
            env['cursando_var'].set.assert_not_called()


if __name__ == '__main__':
    unittest.main()
