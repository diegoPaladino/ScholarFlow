"""Independent report-card extraction data, review and local persistence."""
import json
import os
from pathlib import Path
import re
import tempfile
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation
from datetime import datetime

from student_sync import normalizar
from disciplinas_historico import DISCIPLINAS

PADRAO_GEMUL = {normalizar(nome): nome for nome in DISCIPLINAS}


SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'numero_matricula': {'type': 'string'}, 'nome_aluno': {'type': 'string'},
        'ano': {'type': 'string'}, 'turma': {'type': 'string'},
        'notas': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {key: {'type': 'string'} for key in ('disciplina', 'bimestre', 'nota')},
            'required': ['disciplina', 'bimestre', 'nota'],
        }},
    },
    'required': ['numero_matricula', 'nome_aluno', 'ano', 'turma', 'notas'],
}


def validar(resultado, matricula, nome_esperado='', *, ano_selecionado=None):
    matricula = re.sub(r'\D', '', str(matricula))
    if len(matricula) != 9:
        raise ValueError('Informe a matrícula com nove dígitos antes de ler o boletim.')
    extraida = re.sub(r'\D', '', str(resultado.get('numero_matricula') or ''))
    if 'numero_matricula_origem' in resultado and extraida != matricula:
        raise ValueError('Este boletim já está vinculado a outra matrícula do GEMUL.')
    # A transferred student's source school uses its own registration numbering.
    origem = str(resultado.get('numero_matricula_origem') or
                 (resultado.get('numero_matricula') if extraida != matricula else '') or '').strip()
    nome = str(resultado.get('nome_aluno') or '').strip()
    if nome_esperado and (not nome or SequenceMatcher(None, normalizar(nome), normalizar(nome_esperado)).ratio() < 0.92):
        raise ValueError('O nome do boletim difere do aluno selecionado. Confira o documento antes de vincular.')
    ano = str(ano_selecionado if ano_selecionado is not None else resultado.get('ano') or '').strip()
    if not re.fullmatch(r'\d{4}', ano):
        if ano_selecionado is not None:
            raise ValueError('Selecione um ano válido com quatro dígitos na interface antes de ler o boletim.')
        raise ValueError('Não foi identificado um ano letivo válido no boletim. Confira o documento.')
    notas, identidades = [], {}
    ignoradas = list(resultado.get('disciplinas_ignoradas') or [])
    for item in resultado.get('notas', []):
        nome = str(item.get('disciplina') or '').strip()
        chave_disciplina = _chave_disciplina(nome)
        if chave_disciplina not in PADRAO_GEMUL:
            if nome and nome not in ignoradas:
                ignoradas.append(nome)
            continue
        nome = PADRAO_GEMUL[chave_disciplina]
        bimestre = str(item.get('bimestre') or '').strip()
        nota = str(item.get('nota') or '').strip().replace(',', '.')
        if not nota or re.fullmatch(r'[-–—]+', nota):
            continue
        if not nome or bimestre not in {'1', '2', '3', '4'}:
            raise ValueError('Disciplina ou bimestre inválido na leitura do boletim.')
        try:
            valor = Decimal(nota)
        except InvalidOperation:
            raise ValueError(f'Nota não numérica em {nome}, bimestre {bimestre}: {nota}.') from None
        if not valor.is_finite() or not 0 <= valor <= 10:
            raise ValueError(f'Nota fora de 0 a 10 em {nome}, bimestre {bimestre}.')
        chave = (chave_disciplina, bimestre)
        if chave in identidades:
            if identidades[chave] != valor:
                raise ValueError(f'Notas conflitantes em {nome}, bimestre {bimestre}.')
            continue
        identidades[chave] = valor
        notas.append({'disciplina': nome, 'bimestre': bimestre, 'nota': format(valor, 'f')})
    if not notas:
        raise ValueError('Nenhuma nota bimestral legível das disciplinas padrão do GEMUL encontrada no boletim.')
    return dict(numero_matricula=matricula, nome_aluno=str(resultado.get('nome_aluno') or '').strip(),
                numero_matricula_origem=origem, disciplinas_ignoradas=ignoradas,
                ano=ano, turma=str(resultado.get('turma') or '').strip(), notas=notas)


def linhas_conferencia(notas):
    """One subject per row; empty terms remain empty rather than becoming zero."""
    linhas = {}
    for item in notas:
        nome = item['disciplina']
        linha = linhas.setdefault(nome, [nome, '', '', '', ''])
        indice = int(item['bimestre'])
        if indice not in range(1, 5):
            raise ValueError('Bimestre inválido na conferência.')
        nota = str(item['nota'])
        if linha[indice] and not notas_equivalentes_conferencia(linha[indice], nota):
            raise ValueError(f'Notas conflitantes em {nome}, bimestre {indice}.')
        linha[indice] = nota
    return list(linhas.values())


def notas_equivalentes_conferencia(a, b):
    return Decimal(a.replace(',', '.')) == Decimal(b.replace(',', '.'))


def notas_da_conferencia(linhas):
    return [dict(disciplina=linha[0], bimestre=str(bimestre), nota=str(nota).strip())
            for linha in linhas for bimestre, nota in enumerate(linha[1:], start=1)
            if str(nota).strip()]


def caminho_cache(base_dir, matricula):
    matricula = re.sub(r'\D', '', str(matricula))
    if len(matricula) != 9:
        raise ValueError('Matrícula inválida para recuperar o boletim.')
    return Path(base_dir) / 'cache_boletins_matricula' / f'{matricula}.json'


def carregar(base_dir, matricula):
    path = caminho_cache(base_dir, matricula)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('matricula') != matricula:
        raise ValueError('O cache do boletim não corresponde à matrícula selecionada.')
    return payload


def salvar(base_dir, matricula, resultado, arquivos, nome_esperado='', *, ano_selecionado=None):
    resultado = validar(resultado, matricula, nome_esperado, ano_selecionado=ano_selecionado)
    path = caminho_cache(base_dir, matricula)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = carregar(base_dir, matricula) or {'matricula': matricula, 'boletins': {}}
    payload['boletins'][resultado['ano']] = resultado
    payload['ultimo_ano'] = resultado['ano']
    payload['arquivos'] = list(arquivos)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            json.dump(payload, file, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return resultado


def exigir_ano_corrente(resultado):
    ano = str(datetime.now().year)
    if str(resultado['ano']).strip() != ano:
        raise ValueError(f'O lançamento bimestral usa o ano corrente ({ano}). '
                         f'O boletim informado é de {resultado["ano"]}; confira o documento.')
    return ano


def turma_do_cadastro(registros, matricula, alternativa=''):
    turmas = {str(r.get('turma') or '').strip() for r in registros
              if str(r.get('matricula') or '').strip() == matricula and str(r.get('turma') or '').strip()}
    if len({_chave_turma(t) for t in turmas}) > 1:
        raise ValueError('Há turmas diferentes para esta matrícula no cadastro. Confira a base de alunos.')
    if turmas:
        return sorted(turmas)[0]
    if alternativa.strip():
        return alternativa.strip()
    raise ValueError('Turma não encontrada no cadastro do aluno. Informe a turma do GEMUL na revisão.')


def _opcoes(campo):
    return campo.evaluate('el => Array.from(el.options).map(o => ({value:o.value, label:o.textContent.trim()}))')


def _chave_turma(nome):
    return normalizar(re.sub(r'(?<=\d)[º°ª]', '', str(nome)))


def _chave_disciplina(nome):
    chave = normalizar(nome)
    return {'ARTE': 'ARTES', 'PORTUGUES': 'LINGUA PORTUGUESA',
            'CIENCIAS DA NATUREZA': 'CIENCIAS',
            'PRATICAS DE LEITURA E ESCRITA': 'PRATICA DE LEITURA E ESCRITA'}.get(chave, chave)


def _opcao_unica(campo, rotulo, turma=False):
    opcoes = [op for op in _opcoes(campo) if op['value'] not in {'', '0'}]
    if turma:
        matches = [op for op in opcoes if _chave_turma(op['label']) == _chave_turma(rotulo)]
        if not matches:
            matches = [op for op in opcoes if _chave_turma(op['label'].split('-', 1)[-1]) == _chave_turma(rotulo)
                       or _chave_turma(op['label'].split('-', 1)[0]) == _chave_turma(rotulo)]
    else:
        matches = [op for op in opcoes if _chave_disciplina(op['label']) == _chave_disciplina(rotulo)]
    if not matches and not turma:
        raise DisciplinaNaoDisponivel(rotulo)
    if len(matches) != 1:
        raise RuntimeError(f'Opção não encontrada de forma única no GEMUL: {rotulo}. Confira a turma e a disciplina.')
    return matches[0]


def _selecionar(pagina, seletor, valor, timeout_ms):
    campo = pagina.locator(seletor)
    if campo.input_value() != valor:
        with pagina.expect_navigation(wait_until='domcontentloaded', timeout=timeout_ms):
            campo.select_option(valor)


def preparar_tela(pagina, base_url, resultado, turma, disciplina, timeout_ms=15000):
    """Open the current-year filters and include transferred students."""
    ano_corrente = exigir_ano_corrente(resultado)
    pagina.goto(base_url.rstrip('/') + '/app/sca_lancamento_notasCon.asp', wait_until='domcontentloaded')
    ano = pagina.locator('#txtAnoLetivo')
    ano.wait_for(state='visible', timeout=timeout_ms)
    if ano.input_value().strip() != ano_corrente:
        ano.fill(ano_corrente)
        with pagina.expect_navigation(wait_until='domcontentloaded', timeout=timeout_ms):
            ano.press('Tab')
    semestre = pagina.locator('#cmbSemestre')
    opcoes = _opcoes(semestre)
    anual = [op for op in opcoes if normalizar(op['label']) == 'ANUAL']
    if len(anual) != 1:
        raise RuntimeError('Semestre anual não identificado na tela do GEMUL.')
    if semestre.input_value() != anual[0]['value']:
        with pagina.expect_navigation(wait_until='domcontentloaded', timeout=timeout_ms):
            semestre.select_option(anual[0]['value'])
    opcao_turma = _opcao_unica(pagina.locator('#cmbTurma'), turma, turma=True)
    _selecionar(pagina, '#cmbTurma', opcao_turma['value'], timeout_ms)
    opcao_disciplina = _opcao_unica(pagina.locator('#cmbDisciplinaTurma'), disciplina)
    _selecionar(pagina, '#cmbDisciplinaTurma', opcao_disciplina['value'], timeout_ms)
    situacoes = pagina.locator('#cmbativos')
    todas = [op for op in _opcoes(situacoes) if normalizar(op['label']) == 'TODAS AS SITUACOES']
    if len(todas) != 1:
        raise RuntimeError('Filtro Todas as Situações não identificado no GEMUL.')
    _selecionar(pagina, '#cmbativos', todas[0]['value'], timeout_ms)
    if pagina.locator('#txtAnoLetivo').input_value().strip() != ano_corrente:
        raise RuntimeError('O ano exibido no GEMUL não corresponde ao ano do boletim.')
    if (pagina.locator('#cmbTurma').input_value() != opcao_turma['value'] or
            pagina.locator('#cmbDisciplinaTurma').input_value() != opcao_disciplina['value']):
        raise RuntimeError('A turma ou disciplina foi alterada durante o carregamento dos filtros do GEMUL.')
    return 'Filtros do boletim abertos no GEMUL. Nenhuma nota foi gravada nesta etapa.'


def _abrir_aluno(pagina, base_url, resultado, turma, disciplina, timeout_ms):
    preparar_tela(pagina, base_url, resultado, turma, disciplina, timeout_ms)
    turma_id = pagina.locator('#cmbTurma').input_value()
    disciplina_id = pagina.locator('#cmbDisciplinaTurma').input_value()
    linhas = pagina.locator('tr').filter(has=pagina.locator('input[type="checkbox"][name="chkAluno"]'))
    alunos = linhas.evaluate_all('''rows => rows.map(row => ({
        matriculas: Array.from(row.cells).map(c => c.textContent.trim()).filter(t => /^\d{9}$/.test(t)),
        codigo: row.querySelector('input[name="chkAluno"]').value
    }))''')
    indices = [i for i, aluno in enumerate(alunos) if resultado['numero_matricula'] in aluno['matriculas']]
    if len(indices) != 1:
        raise RuntimeError(f'Matrícula {resultado["numero_matricula"]} não encontrada de forma única '
                           'na turma, mesmo com Todas as Situações.')
    checks = pagina.locator('input[type="checkbox"][name="chkAluno"]')
    for i in range(checks.count()):
        checks.nth(i).set_checked(False)
    linha = linhas.nth(indices[0])
    codigo_aluno = alunos[indices[0]]['codigo']
    linha.locator('input[name="chkAluno"]').set_checked(True)
    if pagina.locator('input[type="checkbox"][name="chkAluno"]:checked').count() != 1:
        raise RuntimeError('A seleção do aluno não ficou restrita a uma matrícula.')
    with pagina.expect_navigation(wait_until='domcontentloaded', timeout=timeout_ms):
        pagina.locator('#cmbCadastrar').click()
    return _conferir_formulario(pagina, resultado, turma_id, disciplina_id, codigo_aluno), (turma_id, disciplina_id, codigo_aluno)


def _conferir_formulario(pagina, resultado, turma_id, disciplina_id, codigo_aluno):
    for seletor, esperado in (('#txtAnoLetivo', exigir_ano_corrente(resultado)),
                              ('[name="cmbTurma"]', turma_id),
                              ('#cmbDisciplinaTurma', disciplina_id),
                              ('[name="qtdeAluno"]', '1'), ('[name="chkAluno"]', codigo_aluno)):
        campo = pagina.locator(seletor)
        if campo.count() != 1 or campo.input_value().strip() != esperado:
            raise RuntimeError('O formulário de notas não corresponde ao ano, turma, disciplina ou aluno selecionado.')
    linhas = pagina.locator('tr').filter(has=pagina.locator('input[name^="txtCodAluno_"]'))
    if linhas.count() != 1:
        raise RuntimeError('A página de notas precisa conter somente o aluno selecionado.')
    linha = linhas.first
    matriculas = linha.evaluate('row => Array.from(row.cells).map(c => c.textContent.trim())')
    if resultado['numero_matricula'] not in matriculas:
        raise RuntimeError('A matrícula na página de notas difere do aluno em tratamento.')
    codigo = linha.locator('input[name^="txtCodAluno_"]')
    if codigo.input_value() != codigo_aluno:
        raise RuntimeError('O código interno do aluno difere da matrícula selecionada.')
    indice = codigo.get_attribute('name').removeprefix('txtCodAluno_')
    for bimestre in range(4):
        campo = linha.locator(f'[name="txtNota_{indice}_{bimestre:02d}"]')
        if campo.count() != 1:
            raise RuntimeError('Os quatro campos bimestrais não foram identificados no formulário do aluno.')
    # In the supplied GEMUL DOM these metadata inputs appear after </form>.
    # Explicit form ownership preserves the site's own fields in a native submit.
    pagina.evaluate('''() => {
        const form = document.querySelector('#frm');
        const names = new Set(['strQuantNotasBimAtual', 'qtdeAluno', 'cmbPeriodo', 'cmbSemestre',
            'chkTipoNota', 'cmbTurma', 'cmbTurmaProfessor', 'cmbTurno', 'chkAluno',
            'cmbTipoLancamento', 'cmbCurso', 'txtSemestre', 'txtPaginaRetorno', 'buscaHistorico']);
        for (const el of document.querySelectorAll('input[type="hidden"]')) {
            if (!el.form && (names.has(el.name) || el.name.startsWith('txtHidden')))
                el.setAttribute('form', form.id);
        }
    }''')
    return linha, indice


def _valores(linha):
    return linha.locator('input[name^="txtNota_"]').evaluate_all(
        'els => Object.fromEntries(els.map(el => [el.name, el.value.trim()]))')


def _iguais(a, b):
    a, b = str(a).strip().replace(',', '.'), str(b).strip().replace(',', '.')
    try:
        return Decimal(a) == Decimal(b)
    except InvalidOperation:
        return a == b


class LancamentoIncompleto(RuntimeError):
    pass


class DisciplinaNaoDisponivel(RuntimeError):
    pass


def lancar(pagina, base_url, resultado, turma, progresso=None, timeout_ms=15000):
    """Submit only reviewed bimonthly grades and independently reopen to verify them."""
    resultado = validar(resultado, resultado['numero_matricula'])
    exigir_ano_corrente(resultado)
    grupos = {}
    for nota in resultado['notas']:
        chave = _chave_disciplina(nota['disciplina'])
        grupo = grupos.setdefault(chave, {'disciplina': nota['disciplina'], 'notas': {}})
        bimestre = nota['bimestre']
        if bimestre in grupo['notas'] and not _iguais(grupo['notas'][bimestre], nota['nota']):
            raise ValueError(f'Notas conflitantes entre nomes equivalentes de {grupo["disciplina"]}.')
        grupo['notas'][bimestre] = nota['nota']
    confirmadas, gravadas = [], []
    ignoradas = list(resultado.get('disciplinas_ignoradas', []))
    notas_confirmadas = 0
    try:
        for grupo in grupos.values():
            disciplina = grupo['disciplina']
            if progresso:
                progresso(f'Conferindo {disciplina} para {resultado["numero_matricula"]}...')
            try:
                (linha, indice), identidades = _abrir_aluno(pagina, base_url, resultado, turma, disciplina, timeout_ms)
            except DisciplinaNaoDisponivel:
                ignoradas.append(disciplina)
                continue
            antes = _valores(linha)
            esperados = dict(antes)
            for bimestre, nota in grupo['notas'].items():
                nome = f'txtNota_{indice}_{int(bimestre) - 1:02d}'
                campo = linha.locator(f'[name="{nome}"]')
                esperados[nome] = nota
                if not _iguais(antes[nome], nota):
                    if not campo.is_enabled() or not campo.is_editable():
                        raise RuntimeError(f'{disciplina}, {bimestre}º bimestre: campo bloqueado para edição no GEMUL.')
                    campo.fill(nota.replace('.', ','))
                    campo.press('Tab')
                    if not _iguais(campo.input_value(), nota):
                        raise RuntimeError(f'O GEMUL recusou a nota de {disciplina}, {bimestre}º bimestre.')
            mudou = any(not _iguais(antes[nome], valor) for nome, valor in esperados.items())
            if mudou:
                salvar = pagina.get_by_role('button', name='Salvar Notas', exact=True)
                with pagina.expect_navigation(wait_until='domcontentloaded', timeout=timeout_ms):
                    with pagina.expect_response(lambda r: r.request.method == 'POST' and
                            r.url.split('?')[0].endswith('/sca_lancamento_notas_cod.asp'), timeout=timeout_ms) as resposta:
                        salvar.click()
                if not 200 <= resposta.value.status < 400:
                    raise RuntimeError(f'O GEMUL não confirmou o envio das notas de {disciplina}.')
                gravadas.append(disciplina)
            # Reopen through the filters instead of trusting the just-submitted form.
            (linha, novo_indice), novas_identidades = _abrir_aluno(pagina, base_url, resultado, turma, disciplina, timeout_ms)
            if novas_identidades != identidades:
                raise RuntimeError('A identidade do formulário mudou após salvar as notas.')
            salvos = _valores(linha)
            for nome, valor in esperados.items():
                novo_nome = nome.replace(f'txtNota_{indice}_', f'txtNota_{novo_indice}_', 1)
                if novo_nome not in salvos or not _iguais(salvos[novo_nome], valor):
                    raise RuntimeError(f'Nota não confirmada após reabrir {disciplina}: {novo_nome}.')
            confirmadas.append(disciplina)
            notas_confirmadas += len(grupo['notas'])
    except Exception as exc:
        pendentes = [g['disciplina'] for g in grupos.values()
                     if g['disciplina'] not in confirmadas and g['disciplina'] not in ignoradas]
        detalhe = (f'Disciplinas confirmadas: {", ".join(confirmadas) or "nenhuma"}. '
                   f'Pendentes de conferência: {", ".join(pendentes)}. ')
        if gravadas:
            detalhe += f'Envio já realizado para: {", ".join(gravadas)}. '
        raise LancamentoIncompleto(detalhe + str(exc)) from exc
    return {'disciplinas': confirmadas, 'notas': notas_confirmadas, 'ignoradas': ignoradas,
            'mensagem': (f'{notas_confirmadas} notas bimestrais confirmadas no GEMUL em {len(confirmadas)} disciplinas.'
                         if confirmadas else 'Nenhuma disciplina do boletim está disponível para lançamento nesta turma do GEMUL.')}
