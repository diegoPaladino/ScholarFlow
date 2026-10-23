import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, call, patch


class LoginTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                 and node.name in {'solicitar_credenciais_gemul', 'logar_pw'}]
        self.env = dict(os=os, credenciais_locais=Mock(), messagebox=Mock(),
                        simpledialog=Mock(), tk=Mock(), ttk=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<login>', 'exec'), self.env)

    def login(self, url, login_form_counts=(0,), credentials=None):
        credentials = credentials or [('teste', 'senha_teste', True)]
        provider = Mock(side_effect=credentials)
        self.env['solicitar_credenciais_gemul'] = provider
        page = Mock(url=url)
        form = page.locator.return_value
        form.count.side_effect = login_form_counts
        return page, provider

    def test_saved_credentials_skip_dialog(self):
        self.env['credenciais_locais'].carregar.return_value = {'usuario': 'teste', 'senha': 'senha_teste'}
        with patch.dict(os.environ, {}, clear=True):
            result = self.env['solicitar_credenciais_gemul']()
        self.assertEqual(result, ('teste', 'senha_teste', True))
        self.env['simpledialog'].Dialog.assert_not_called()

    def test_school_selection_redirect_saves_credentials(self):
        page, _ = self.login('https://gemul-aparecida.com.br/login/selecionar_escola.asp')
        self.env['logar_pw'](page)
        self.env['credenciais_locais'].salvar.assert_called_once_with('teste', 'senha_teste')

    def test_direct_app_redirect_saves_credentials(self):
        page, _ = self.login('https://gemul-aparecida.com.br/app/academico.asp')
        self.env['logar_pw'](page)
        self.env['credenciais_locais'].salvar.assert_called_once_with('teste', 'senha_teste')

    def test_rejected_credentials_reopen_dialog_and_save_correction(self):
        page, provider = self.login('https://gemul-aparecida.com.br/login/selecionar_escola.asp', (1, 0),
                                   [('antigo', 'senha_antiga', True), ('novo', 'senha_nova', True)])
        self.env['logar_pw'](page)
        self.assertEqual(provider.call_args_list, [call(forcar_dialogo=False), call(forcar_dialogo=True)])
        self.env['credenciais_locais'].salvar.assert_called_once_with('novo', 'senha_nova')

    def test_failed_login_does_not_save_credentials(self):
        page, _ = self.login('https://gemul-aparecida.com.br/login.asp', (1, 1),
                             [('teste', 'errada', True)] * 2)
        with self.assertRaisesRegex(RuntimeError, 'não aceitou'):
            self.env['logar_pw'](page)
        self.env['credenciais_locais'].salvar.assert_not_called()

    def test_unconfirmed_redirect_does_not_save_credentials(self):
        page, _ = self.login('https://gemul-aparecida.com.br/default.asp')
        with self.assertRaisesRegex(RuntimeError, 'não confirmou'):
            self.env['logar_pw'](page)
        self.env['credenciais_locais'].salvar.assert_not_called()

    def test_remember_unchecked_does_not_save_credentials(self):
        page, _ = self.login('https://gemul-aparecida.com.br/app/academico.asp',
                             credentials=[('teste', 'senha_teste', False)])
        self.env['logar_pw'](page)
        self.env['credenciais_locais'].salvar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
