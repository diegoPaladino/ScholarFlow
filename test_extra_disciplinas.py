import ast
from pathlib import Path
import re
import unittest
from typing import Any, Dict
from unittest.mock import Mock

import disciplinas_historico
from student_sync import normalizar


class ExtraPipelineTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        names = {'normalizar_registro_historico', 'mesclar_registro_historico',
                 'cadastrar_disciplinas_com_extras', 'mapear_disciplina_para_chave_nota'}
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.module = Mock()
        self.env = dict(Dict=Dict, Any=Any, normalizar_texto_busca=normalizar,
            DISCIPLINA_EQUIVALENCIAS={'MATEMATICA': 'nota_matematica'},
            converter_conceitos_em_observacoes=lambda x: x,
            extrair_ano_4_digitos=lambda x: str(x), normalizar_serie=lambda x: x,
            normalizar_cursando_por_ano=lambda *args: 'nao', CHAVES_NOTAS=[],
            limpar_nota_extraida=lambda x: x, nota_deve_ser_lancada=lambda x: bool(x),
            aplicar_equivalencias_de_disciplinas=Mock(), disciplinas_historico=self.module,
            montar_disciplinas_notas_interface=lambda d: {}, GEMUL_HISTORICO_URL='https://gemul.test/list',
            indice_registro_historico=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<extras>', 'exec'), self.env)

    def test_extra_subjects_survive_year_normalization_and_merge(self):
        extras = [{'disciplina': 'Praticas de Leitura e Escrita', 'nota': '8.1'},
                  {'disciplina': 'Laboratorio de Matematica', 'nota': '7.8'}]
        registro = self.env['normalizar_registro_historico']({'ano': '2024', 'disciplinas_extra': extras})
        self.assertEqual(registro['disciplinas_extra'], extras)
        novo = {'disciplinas_extra': [{'disciplina': 'Estudos Matematicos', 'nota': '9'}]}
        merged = self.env['mesclar_registro_historico'](registro, novo)
        self.assertEqual(len(merged['disciplinas_extra']), 3)
        self.assertEqual(len(registro['disciplinas_extra']), 2)

    def test_unavailable_subjects_are_saved_before_success_summary(self):
        def save(*args, **kwargs):
            kwargs['resumo'].update(extras_lancadas=['Pratica: 8.1'],
                extras_ausentes=[{'disciplina': 'Outra', 'nota': '7.8'}])
            return 1
        self.module.cadastrar.side_effect = save
        dados = dict(numero_matricula='202626234', serie='3 ANO', nome_escola='ESCOLA', disciplinas_extra=[])
        self.assertEqual(self.env['cadastrar_disciplinas_com_extras'](Mock(), '2024', dados), 1)
        self.module.acrescentar_observacao.assert_called_once()
        self.assertIn('Outra: 7.8', self.module.acrescentar_observacao.call_args.args[5])
        self.assertIn('Pratica: 8.1', dados['resumo_disciplinas_extra'])
        self.assertIn('Outra: 7.8', dados['resumo_disciplinas_extra'])

    def test_grade_numeric_equivalence_keeps_real_differences(self):
        for grade in ('8', '8.0', '8,00'):
            self.assertTrue(disciplinas_historico.notas_equivalentes(grade, '8.000'))
        self.assertFalse(disciplinas_historico.notas_equivalentes('8', '8.1'))
        self.assertFalse(disciplinas_historico.notas_equivalentes('', '0'))


class ObservationFilterTests(unittest.TestCase):
    def test_extra_summary_removed_and_other_observations_preserved(self):
        text = ('Historico transcrito conforme original. '
                'Disciplinas extras/complementares registradas neste ano: '
                'Praticas de Leitura e Escrita (7,2); Estudos matematicos (6,6). '
                'Resultado Final: Aprovado. Dias letivos: 202.')
        result = disciplinas_historico.limpar_observacao(text)
        self.assertEqual(result, 'Historico transcrito conforme original. Resultado Final: Aprovado. Dias letivos: 202.')

    def test_concepts_only_keep_subjects_missing_from_catalog(self):
        text = 'Aluno(a) recebeu o conceito "A" nas materias Artes e Outra disciplina. Texto relevante.'
        result = disciplinas_historico.limpar_observacao(text, ['ARTES'])
        self.assertNotIn('Artes', result)
        self.assertIn('Outra disciplina', result)
        self.assertIn('Texto relevante.', result)
        self.assertEqual(disciplinas_historico.limpar_observacao(result, ['ARTES']), result)

    def test_known_extra_concept_removed(self):
        text = 'Aluno(a) recebeu o conceito "A" na materia Estudos Matematicos.'
        self.assertEqual(disciplinas_historico.limpar_observacao(text, ['Estudos Matematicos']), '')


    def test_general_observation_is_only_local(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'escrever_observacoes')
        processor = Mock()
        processor.decisao_texto.return_value = 'Texto do ano.'
        page, functions = Mock(), Mock()
        env = dict(ProcessamentoDeObservacoes=lambda: processor,
            mesclar_textos_observacao=lambda a, b: a,
            corrigir_texto_utf8=lambda text: text,
            mover_continuidade_estudos_para_final=lambda text: text,
            disciplinas_historico=disciplinas_historico, FuncoesDoPrograma=functions,
            _get_base=lambda driver: page)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<write-observation>', 'exec'), env)
        env[node.name](page, '2024', 'ESCOLA', 'CIDADE', 'nao', 'nao', '', '1 ANO', '800', 'Conferencia local')
        page.locator.assert_called_once_with('#txtObservacaoGeral')
        page.locator.return_value.fill.assert_called_once_with('')
        texts = [call.args[2] for call in functions.escrever_texto.call_args_list]
        self.assertNotIn('Conferencia local', texts)
        self.assertIn('Texto do ano.', texts)
