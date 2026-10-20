import ast
from datetime import datetime
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Dict
import unittest
from unittest.mock import Mock, patch

import credenciais_locais
from student_sync import normalizar


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        source = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        wanted = {'executar_lancamento_historico', 'indice_registro_historico',
                  'normalizar_serie', 'gerar_texto_cobranca_historico'}
        nodes = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
        self.page = Mock()
        self.page.locator.return_value.input_value.return_value = '202654726'
        self.env = dict(Dict=Dict, Any=Any, re=re, datetime=datetime, time=Mock(time=Mock(return_value=1)),
                        normalizar_texto_busca=normalizar, ORDINAL_INDICATOR=chr(186),
                        normalizar_cursando_por_ano=lambda *args: 'nao',
                        matricula_deve_historico=Mock(return_value=False),
                        garantir_sessao_gemul=Mock(return_value=self.page),
                        exigir_ano_4_digitos=lambda ano: ano,
                        _get_base=lambda page: page, registrar_etapa_historico=Mock(),
                        sessao_execucao={}, UF_ESCOLA_PADRAO='GO', ESCOLA_PADRAO='ESCOLA A',
                        GEMUL_HISTORICO_URL='https://example.test/app/sca_historico_escolar_novoCon.asp',
                        SerieEscolhida=Mock(), Atalho=Mock(), formatar_duracao=lambda value: '00:01')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<workflow>', 'exec'), self.env)
        self.data = dict(numero_matricula='202654726', nome_aluno='ALUNA TESTE',
                         serie='3 ANO', ano='2026', nome_escola='ESCOLA A', cidade='CIDADE',
                         carga_horaria='215', ja_estudou='nao', ficha_descritiva='nao',
                         txt_observacoes='', cursando='nao')

    def test_existing_record_stops_before_opening_or_inserting(self):
        self.page.locator.return_value.filter.return_value.evaluate_all.return_value = [
            ['2026', 'Anual', 'ESCOLA A', 'ENSINO FUNDAMENTAL', '3 ANO']]
        result = self.env['executar_lancamento_historico'](self.data)
        self.assertIn('já existente', result)
        self.assertFalse(self.env['SerieEscolhida'].mock_calls)
        self.page.get_by_role.assert_not_called()
        self.page.locator.return_value.filter.return_value.nth.assert_not_called()
        self.env['Atalho'].alerta_sonoro.assert_not_called()

    def test_debtor_blocked_before_browser_access(self):
        for persisted in (True, False):
            self.env['matricula_deve_historico'].return_value = persisted
            data = dict(self.data, deve_historico=not persisted)
            with self.assertRaisesRegex(ValueError, 'pendente'):
                self.env['executar_lancamento_historico'](data)
        self.env['garantir_sessao_gemul'].assert_not_called()

    def test_new_record_continues_to_correct_series(self):
        self.page.locator.return_value.filter.return_value.evaluate_all.return_value = [
            ['2025', 'Anual', 'ESCOLA A', 'ENSINO FUNDAMENTAL', '3 ANO']]
        result = self.env['executar_lancamento_historico'](self.data)
        self.assertIn('concluido', result)
        self.env['SerieEscolhida'].ano3.assert_called_once()

    def test_wrong_student_blocked(self):
        self.page.locator.return_value.input_value.return_value = '111111111'
        with self.assertRaisesRegex(RuntimeError, 'matrícula'):
            self.env['executar_lancamento_historico'](self.data)
        self.assertFalse(self.env['SerieEscolhida'].mock_calls)

    def test_request_uses_student_and_school_without_invented_deadline(self):
        text = self.env['gerar_texto_cobranca_historico'](self.data)
        for value in ('ALUNA TESTE', '202654726', 'ESCOLA A', 'histórico escolar'):
            self.assertIn(value, text)
        self.assertLess(len(text.split()), 65)
        with self.assertRaises(ValueError):
            self.env['gerar_texto_cobranca_historico']({})

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_windows_credentials_roundtrip_and_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'credentials.dpapi'
            with patch.object(credenciais_locais, 'ARQUIVO', path):
                self.assertEqual(credenciais_locais.carregar(), {})
                credenciais_locais.salvar('usuario_teste', 'senha_teste_123')
                self.assertNotIn(b'senha_teste_123', path.read_bytes())
                self.assertEqual(credenciais_locais.carregar(),
                                 dict(usuario='usuario_teste', senha='senha_teste_123'))
                credenciais_locais.esquecer()
                self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
