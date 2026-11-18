import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

import sessao_gemul as sessao


class SessaoTests(unittest.TestCase):
    def setUp(self):
        self.pagina = Mock(url='https://gemul.test/app/historico.asp')
        self.pagina.is_closed.return_value = False
        self.pagina.locator.return_value.is_visible.return_value = False
        self.progresso = Mock()

    def test_authenticated_page(self):
        self.assertFalse(sessao.sessao_expirada(self.pagina))

    def test_login_urls_and_embedded_login(self):
        for path in ('/login.asp', '/default.asp', '/login/selecionar_escola.asp'):
            self.pagina.url = 'https://gemul.test' + path
            self.assertTrue(sessao.sessao_expirada(self.pagina))
        self.pagina.url = 'https://gemul.test/app/historico.asp'
        self.pagina.locator.return_value.is_visible.return_value = True
        self.assertTrue(sessao.sessao_expirada(self.pagina))

    def test_server_probe_detects_expiration_despite_stale_form(self):
        target = 'https://gemul.test/app/historico.asp'
        def navegar(url, **kwargs):
            self.pagina.url = target if login.called else 'https://gemul.test/login.asp'
        login = Mock()
        menu = Mock()
        self.pagina.goto.side_effect = navegar
        sessao.abrir_historico_autenticado(self.pagina, target, login, menu, self.progresso)
        login.assert_called_once_with(self.pagina)
        menu.assert_called_once_with(self.pagina, apos_login=True)
        self.assertEqual(self.pagina.goto.call_count, 2)
        self.pagina.locator.return_value.wait_for.assert_called_once()

    def test_active_probe_does_not_login(self):
        login = Mock()
        sessao.abrir_historico_autenticado(self.pagina, self.pagina.url, login, Mock(), self.progresso)
        login.assert_not_called()

    def run_operation(self, action, recover):
        return sessao.executar_com_recuperacao(action, lambda: self.pagina, recover, self.progresso)

    def test_logout_during_write_recovers_once_and_resumes(self):
        action = Mock(side_effect=[sessao.SessaoExpirada('expirou'), 'conferido'])
        recover = Mock()
        self.assertEqual(self.run_operation(action, recover), 'conferido')
        recover.assert_called_once()
        self.assertEqual(action.call_count, 2)

    def test_timeout_on_login_page_is_recovered(self):
        self.pagina.url = 'https://gemul.test/login.asp'
        def recuperar():
            self.pagina.url = 'https://gemul.test/app/historico.asp'
        action = Mock(side_effect=[TimeoutError('campo ausente'), 'conferido'])
        self.assertEqual(self.run_operation(action, recuperar), 'conferido')

    def test_repeated_logout_stops_instead_of_looping(self):
        action = Mock(side_effect=sessao.SessaoExpirada('expirou'))
        recover = Mock()
        with self.assertRaisesRegex(sessao.SessaoExpirada, 'novamente'):
            self.run_operation(action, recover)
        self.assertEqual(action.call_count, 2)
        recover.assert_called_once()

    def test_unrelated_write_error_is_never_retried(self):
        action = Mock(side_effect=ValueError('nota inválida'))
        recover = Mock()
        with self.assertRaisesRegex(ValueError, 'nota inválida'):
            self.run_operation(action, recover)
        action.assert_called_once()
        recover.assert_not_called()

    def test_success_redirected_to_login_is_not_reported_as_completed(self):
        self.pagina.url = 'https://gemul.test/login.asp'
        action = Mock(return_value='aparente sucesso')
        with self.assertRaises(sessao.SessaoExpirada):
            self.run_operation(action, Mock())

    def test_closed_browser_is_not_reported_as_success_or_retried(self):
        self.pagina.is_closed.return_value = True
        recover = Mock()
        with self.assertRaisesRegex(RuntimeError, 'fechado'):
            self.run_operation(Mock(return_value='sucesso'), recover)
        recover.assert_not_called()

    def test_cancelled_login_is_not_repeated(self):
        self.pagina.url = 'https://gemul.test/login.asp'
        login = Mock(side_effect=RuntimeError('Login cancelado'))
        def action():
            sessao.abrir_historico_autenticado(self.pagina, self.pagina.url, login, Mock(), self.progresso)
        with self.assertRaisesRegex(sessao.FalhaAutenticacao, 'cancelado'):
            self.run_operation(action, Mock())
        login.assert_called_once()

    def carregar_funcao_sessao(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'garantir_sessao_gemul')
        env = dict(driver=self.pagina, seletor=None, sessao_gemul=sessao,
                   sessao_execucao={'navegador_inicializado': True, 'matricula_atual': ''},
                   _normalizar_matricula_gemul=lambda value: value,
                   navegador_playwright_ativo=lambda: True,
                   garantir_tela_historico_disponivel=Mock(return_value=True),
                   digita_matricula_pw=Mock(), _get_base=lambda page: page)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<session>', 'exec'), env)
        return env

    def test_loading_student_uses_browser_without_foreground_keystrokes(self):
        env = self.carregar_funcao_sessao()
        self.pagina.locator.return_value.input_value.return_value = '202600001'
        self.assertIs(env['garantir_sessao_gemul']('202600001', force_reabrir_tela=True), self.pagina)
        env['garantir_tela_historico_disponivel'].assert_called_once_with(force_reabrir=True)
        env['digita_matricula_pw'].assert_called_once_with(self.pagina, '202600001')
        self.assertEqual(env['sessao_execucao']['matricula_atual'], '202600001')

    def test_loading_wrong_student_does_not_mark_session_ready(self):
        env = self.carregar_funcao_sessao()
        self.pagina.locator.return_value.input_value.return_value = '111111111'
        with self.assertRaisesRegex(RuntimeError, 'matrícula'):
            env['garantir_sessao_gemul']('202600001')
        self.assertEqual(env['sessao_execucao']['matricula_atual'], '')


if __name__ == '__main__':
    unittest.main()
