import ast
from pathlib import Path
from typing import Any, Dict

source = Path(__file__).resolve().with_name('main.py').read_text(encoding='utf-8-sig')
tree = ast.parse(source)
names = {'mesclar_textos_observacao', 'normalizar_registro_historico',
         'mesclar_registro_historico', 'construir_historicos_por_ano', 'escrever_observacoes'}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
schema = next(n.value for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == 'HISTORICO_JSON_SCHEMA' for t in n.targets))
schema = ast.literal_eval(schema)
for obj in [schema, schema['properties']['historicos']['items']]:
    assert set(obj['properties']) == set(obj['required'])
    assert len(obj['required']) == len(set(obj['required']))
    assert 'txt_observacoes_gerais' in obj['required']

env = dict(Any=Any, Dict=Dict, corrigir_texto_utf8=lambda t: str(t or ''),
           converter_conceitos_em_observacoes=lambda r: r,
           extrair_ano_4_digitos=lambda a: str(a) if len(str(a)) == 4 else '',
           normalizar_serie=lambda s: s, normalizar_texto_busca=lambda s: s.upper(),
           normalizar_cursando_por_ano=lambda a, v: v, CHAVES_NOTAS=[],
           aplicar_equivalencias_de_disciplinas=lambda r, s: None)
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<isolated>', 'exec'), env)
data = {'txt_observacoes_gerais': 'Informação geral.', 'historicos': [
    {'ano': '2022', 'txt_observacoes': 'Observação de 2022.', 'txt_observacoes_gerais': 'Informação geral.'},
    {'ano': '2023', 'txt_observacoes': 'Observação de 2023.'}]}
records = env['construir_historicos_por_ano'](data)
assert records['2022']['txt_observacoes'] == 'Observação de 2022.'
assert records['2023']['txt_observacoes'] == 'Observação de 2023.'
assert all(r['txt_observacoes_gerais'] == 'Informação geral.' for r in records.values())
legacy = env['construir_historicos_por_ano']({'historicos': [{'ano': '2020', 'txt_observacoes': 'Texto antigo.'}]})
assert legacy['2020']['txt_observacoes_gerais'] == ''
assert legacy['2020']['txt_observacoes'] == 'Texto antigo.'

class Processing:
    def decisao_texto(self, *args):
        return 'Regra automática.'

class Form:
    calls = {}
    @classmethod
    def escrever_texto(cls, driver, xpath, text):
        cls.calls[xpath] = text

env.update(ProcessamentoDeObservacoes=Processing, FuncoesDoPrograma=Form)
write = env['escrever_observacoes']
write(None, '2022', 'Escola', 'Cidade', 'nao', 'nao', 'Observação de 2022.', '1º ANO', '800', 'Informação geral.')
assert Form.calls['//*[@id="txtObservacao"]'] == 'Regra automática. Observação de 2022.'
assert Form.calls['//*[@id="txtObservacaoGeral"]'] == 'Informação geral.'
Form.calls.clear()
write(None, '2020', 'Escola', 'Cidade', 'nao', 'nao', 'Texto antigo.', '1º ANO', '800')
assert '//*[@id="txtObservacaoGeral"]' not in Form.calls
assert env['mesclar_textos_observacao']('Texto antigo. Regra automática.', 'Texto antigo.') == 'Texto antigo. Regra automática.'
print('OK: schema, separação por ano, observação geral, cache legado e preenchimento dos dois XPaths.')
