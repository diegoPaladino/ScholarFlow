"""Read-only integration tests against the actual legacy functions, without GUI startup."""
import ast
import re
import unicodedata
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from idp_historico_adapter import adapt_historico

NAMES = set('CHAVES_NOTAS DISCIPLINA_EQUIVALENCIAS MARCADORES_TEXTO_CORROMPIDO ORDINAL_INDICATOR ROTULOS_NOTAS_OBSERVACAO SIGLAS_CONCEITO_CONHECIDAS SIGLAS_IGNORADAS_COMO_CONCEITO _decodificar_texto_mojibake_misto aplicar_equivalencias_de_disciplinas construir_historicos_por_ano converter_conceitos_em_observacoes corrigir_texto_utf8 eh_valor_numerico_nota extrair_ano_4_digitos extrair_sigla_conceito gerar_observacao_conceitos limpar_nome_disciplina_observacao limpar_nota_extraida mapear_disciplina_para_chave_nota mesclar_registro_historico mesclar_textos_observacao normalizar_cursando_por_ano normalizar_registro_historico normalizar_serie normalizar_sim_nao normalizar_texto_busca nota_deve_ser_lancada reparar_acentos_mistos'.split())

def load_history():
    path = Path(__file__).with_name('main.py')
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in NAMES) or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in NAMES for t in n.targets))]
    ns = dict(Any=Any, Dict=Dict, List=List, Tuple=Tuple, datetime=datetime, re=re, unicodedata=unicodedata)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return ns['construir_historicos_por_ano']

class HistoryContractTests(unittest.TestCase):
    def convert(self, *rows):
        result = adapt_historico(list(rows), numero_matricula='', nome_aluno='Synthetic')
        return load_history()(result['payload'])
    def row(self, **kw):
        return dict(dict(period_type='annual', ano='2025', serie='1º ANO'), **kw)
    def test_years(self):
        self.assertEqual(list(self.convert(self.row(ano='2024'), self.row())), ['2024','2025'])
    def test_grade(self):
        self.assertEqual(self.convert(self.row(nota_matematica='7,5'))['2025']['nota_matematica'].replace(',','.'), '7.5')
    def test_missing(self):
        self.assertEqual(self.convert(self.row())['2025']['nota_arte'], '')
    def test_concept(self):
        row = self.convert(self.row(nota_arte='A'))['2025']
        self.assertEqual(row['nota_arte'], 'A')
    def test_zero_policy(self):
        # Legacy normalization intentionally suppresses zero; raw review retains it.
        raw = self.row(nota_arte='0')
        self.assertEqual(adapt_historico([raw],numero_matricula='',nome_aluno='Synthetic')['payload']['historicos'][0]['nota_arte'],'0')
        self.assertEqual(self.convert(raw)['2025']['nota_arte'],'')
