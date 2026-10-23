"""Register subjects with a situation determined by the school year."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from student_sync import normalizar


DISCIPLINAS = (
    'ARTES', 'CIÊNCIAS', 'CULTURA DE INOVAÇÃO E TECNOLOGIAS', 'EDUCAÇÃO FÍSICA',
    'ENSINO RELIGIOSO', 'GEOGRAFIA', 'HISTÓRIA', 'LÍNGUA PORTUGUESA', 'MATEMÁTICA',
)


def registros(pagina):
    return pagina.locator('#tbodyDisciplinas tr').evaluate_all("""rows => rows.map(row => ({
        id: row.getAttribute('data-id') || '',
        disciplina: row.querySelector('[name="cmbDisciplina"]')?.selectedOptions[0]?.textContent.trim() || '',
        ch: row.querySelector('[name="txtCH"]')?.value || '',
        media: row.querySelector('[name="txtMedia"]')?.value || '',
        omitir: row.querySelector('[name="txtMostraNota"]')?.checked || false,
        situacao: row.querySelector('[name="cmbSituacaoPromocao"]')?.value || ''
    }))""")


def situacao_por_ano(ano, ano_corrente=None):
    atual = datetime.now().year if ano_corrente is None else ano_corrente
    texto = str(ano).strip()
    if not re.fullmatch(r'\d{4}', texto) or not 1900 <= int(texto) <= atual:
        raise ValueError('Informe um ano letivo válido, até o ano corrente, para lançar as disciplinas.')
    return 'CR' if int(texto) == atual else 'AP'


def notas_equivalentes(a, b):
    a, b = str(a).strip().replace(',', '.'), str(b).strip().replace(',', '.')
    try:
        x, y = Decimal(a), Decimal(b)
        return x.is_finite() and y.is_finite() and x == y
    except InvalidOperation:
        return a == b


def chave_disciplina(nome):
    chave = normalizar(nome)
    return {'PRATICAS DE LEITURA E ESCRITA': 'PRATICA DE LEITURA E ESCRITA'}.get(chave, chave)


def planejar_extras(opcoes, extras):
    encontradas, ausentes = {}, []
    for item in extras or []:
        nome, nota = str(item.get('disciplina', '')).strip(), str(item.get('nota', '')).strip()
        if not nome or not nota:
            continue
        matches = [op for op in opcoes if chave_disciplina(op['label']) == chave_disciplina(nome)]
        if len(matches) > 1:
            raise RuntimeError(f'Disciplina extra ambigua no GEMUL: {nome}.')
        if not matches:
            ausentes.append({'disciplina': nome, 'nota': nota})
            continue
        label = matches[0]['label']
        if label in encontradas and not notas_equivalentes(encontradas[label], nota):
            raise RuntimeError(f'Notas conflitantes para {label}.')
        encontradas[label] = nota
    return encontradas, ausentes


def limpar_observacao(texto, catalogo=DISCIPLINAS):
    """Remove grade summaries; unavailable subjects are appended from structured data."""
    texto = str(texto or '')
    # OCR summaries are redundant with the rows or the structured fallback below.
    texto = re.sub(
        r'Disciplinas extras?(?:/complementares)?(?: complementares)?(?: registradas neste ano)?\s*:[\s\S]*?(?:\.(?=\s+[A-Z\u00c0-\u00dd]|\s*$)|$)',
        '', texto, flags=re.I)
    conhecidos = {chave_disciplina(nome) for nome in catalogo}
    def conceito(match):
        nomes = re.split(r'[,;]\s*|\s+e\s+', match.group('nomes'))
        restantes = [n.strip() for n in nomes if chave_disciplina(n.strip()) not in conhecidos]
        if not restantes:
            return ''
        return match.group('prefixo') + '; '.join(restantes) + '.'
    texto = re.sub(
        r'(?P<prefixo>Aluno\(a\) recebeu o conceito "[^"]+" nas? materias? )(?P<nomes>[^.]+)\.',
        conceito, texto, flags=re.I)
    # Remove individual subject/grade clauses, including aliases seen in source documents.
    for nome in sorted(catalogo, key=len, reverse=True):
        variantes = [nome]
        if chave_disciplina(nome) == 'PRATICA DE LEITURA E ESCRITA':
            variantes += ['Pr\u00e1ticas de Leitura e Escrita']
        for variante in variantes:
            texto = re.sub(re.escape(variante) + r'\s*[:(]\s*\d+(?:[.,]\d+)?\s*\)?[;.]?', '', texto, flags=re.I)
    return re.sub(r'[ \t]{2,}', ' ', texto).strip()


def cadastrar(pagina, ano, timeout_ms=15000, notas=None, extras=None, resumo=None):
    """Add missing subjects and save supplied grades; verify persistence on reload."""
    notas = {normalizar(nome): str(valor).strip().replace(",", ".")
             for nome, valor in (notas or {}).items() if str(valor).strip()}
    situacao = situacao_por_ano(ano)
    pagina.locator('#tbodyDisciplinas').wait_for(state='attached', timeout=timeout_ms)
    ano_pagina = pagina.locator('[name="txtAnoHistorico"]').input_value().strip()
    if ano_pagina != str(ano).strip():
        raise RuntimeError('O ano da página de disciplinas não corresponde ao ano do histórico selecionado.')
    existentes = registros(pagina)
    nomes = [normalizar(row['disciplina']) for row in existentes if row['id']]
    if len(nomes) != len(set(nomes)):
        raise RuntimeError('Há disciplinas duplicadas no GEMUL. Confira antes de continuar.')
    if situacao == 'AP' and any(row['id'] and row['situacao'] == 'CR' for row in existentes):
        raise RuntimeError(
            f'O histórico de {ano} já contém disciplinas como Cursando. '
            'Corrija essas situações para Aprovado no GEMUL antes de continuar. '
            'As notas e cargas horárias existentes foram preservadas.')
    extras_encontradas, ausentes = {}, []

    if extras:
        # Inspect options from an existing row or the page's own row template.
        opcoes = pagina.locator('#tbodyDisciplinas select[name="cmbDisciplina"]').first
        temporaria = not opcoes.count()
        if temporaria:
            pagina.locator('button[onclick="adicionarLinha()"]').click()
            opcoes = pagina.locator('#tbodyDisciplinas select[name="cmbDisciplina"]').last
        catalogo = opcoes.evaluate("el => Array.from(el.options).map(o => ({value:o.value, label:o.textContent.trim()}))")
        if temporaria:
            pagina.locator('#tbodyDisciplinas tr').last.evaluate("el => el.remove()")
        extras_encontradas, ausentes = planejar_extras(catalogo, extras)
        for nome, nota in extras_encontradas.items():
            chave = normalizar(nome)
            if chave in notas and not notas_equivalentes(notas[chave], nota):
                raise RuntimeError(f'Notas conflitantes para {nome}.')
            notas[chave] = nota.replace(',', '.')
    disciplinas_alvo = list(DISCIPLINAS)
    for nome in extras_encontradas:
        if normalizar(nome) not in {normalizar(d) for d in disciplinas_alvo}:
            disciplinas_alvo.append(nome)
    criadas = []
    for disciplina in disciplinas_alvo:
        nota = notas.get(normalizar(disciplina))
        existente = next((row for row in existentes if row['id'] and
                          normalizar(row['disciplina']) == normalizar(disciplina)), None)
        if existente:
            if nota is None or (notas_equivalentes(existente['media'], nota) and not existente['omitir']):
                continue
            linha = pagina.locator(f'#tbodyDisciplinas tr[data-id="{existente["id"]}"]')
        else:
            pagina.locator('button[onclick="adicionarLinha()"]').click()
            linha = pagina.locator('#tbodyDisciplinas tr').last
        seletor = linha.locator('[name="cmbDisciplina"]')
        opcoes = seletor.evaluate("el => Array.from(el.options).map(o => ({value:o.value, label:o.textContent.trim()}))")
        correspondentes = [op for op in opcoes if normalizar(op['label']) == normalizar(disciplina)]
        if len(correspondentes) != 1:
            raise RuntimeError(f'Disciplina não encontrada de forma única no GEMUL: {disciplina}.')
        seletor.select_option(value=correspondentes[0]['value'])
        linha.locator('[name="cmbSituacaoPromocao"]').select_option(value=situacao)
        if not existente:
            linha.locator('[name="txtCH"]').fill('')
        linha.locator('[name="txtMedia"]').fill(nota if nota is not None else '')
        if nota is not None:
            linha.locator('[name="txtMostraNota"]').set_checked(False)
        with pagina.expect_response(
            lambda r: r.request.method == 'POST' and r.url.split('?')[0].endswith(
                '/sca_historico_escolar_novo_disciplina_cod.asp'), timeout=timeout_ms
        ) as resposta:
            linha.locator('button[onclick="salvarLinha(this)"]').click()
        retorno = resposta.value.text().strip()
        if not resposta.value.ok or not re.fullmatch(r'[1-9]\d*', retorno):
            raise RuntimeError(f'O GEMUL não confirmou a gravação da disciplina {disciplina}.')
        pagina.wait_for_function(
            "id => Array.from(document.querySelectorAll('#tbodyDisciplinas tr')).some(r => r.dataset.id === id)",
            arg=retorno, timeout=timeout_ms)
        if not existente:
            criadas.append(disciplina)
            nomes.append(normalizar(disciplina))
    pagina.reload(wait_until='domcontentloaded')
    pagina.locator('#tbodyDisciplinas').wait_for(state='attached', timeout=timeout_ms)
    salvos = registros(pagina)
    for disciplina in disciplinas_alvo:
        encontrados = [row for row in salvos if normalizar(row['disciplina']) == normalizar(disciplina) and row['id']]
        if len(encontrados) != 1:
            raise RuntimeError(f'Disciplina não confirmada após recarregar o GEMUL: {disciplina}.')
        nota = notas.get(normalizar(disciplina))
        if nota is not None and (not notas_equivalentes(encontrados[0]['media'], nota) or encontrados[0]['omitir']):
            raise RuntimeError(f'Nota divergente apos recarregar o GEMUL: {disciplina} (esperada {nota}; encontrada {encontrados[0]["media"]}).')
        if disciplina in criadas and (encontrados[0]['ch'] or (nota is None and encontrados[0]['media']) or encontrados[0]['situacao'] != situacao):
            raise RuntimeError(f'CH, Média ou Situação divergentes após salvar {disciplina}.')
    if resumo is not None:
        labels = pagina.locator('#tbodyDisciplinas select[name="cmbDisciplina"]').first.evaluate(
            "el => Array.from(el.options).map(o => o.textContent.trim())")
        resumo.update(catalogo=labels, extras_lancadas=[f'{nome}: {nota}' for nome, nota in extras_encontradas.items()
                                     if normalizar(nome) not in {normalizar(d) for d in DISCIPLINAS}],
                      extras_ausentes=ausentes)
    return len(criadas)


def acrescentar_observacao(pagina, url_lista, ano, serie, escola, texto, localizar_indice,
                          timeout_ms=15000, catalogo=None, limpar_geral=False):
    """Append to the selected year's existing observation and verify after reopening."""
    def abrir():
        pagina.goto(url_lista, wait_until='domcontentloaded')
        linhas = pagina.locator('tr').filter(has=pagina.locator('button[onclick*="editarDisciplinas"]'))
        linhas.first.wait_for(state='attached', timeout=timeout_ms)
        dados = linhas.evaluate_all("rows => rows.map(row => Array.from(row.cells).map(c => c.innerText.trim()))")
        indice = localizar_indice(dados, ano, serie, escola)
        if indice is None:
            raise RuntimeError('Historico nao encontrado para salvar as disciplinas nas observacoes.')
        linha = linhas.nth(indice)
        botao = linha.get_by_role('button', name=re.compile(r'^(Editar|Alterar)$', re.I))
        if botao.count() != 1:
            botao = linha.locator('button[onclick*="editar" i]:not([onclick*="editarDisciplinas" i]), button[onclick*="alterar" i]')
        if botao.count() != 1:
            raise RuntimeError('Botao de edicao do historico nao identificado; observacoes nao gravadas.')
        botao.click()
        campo = pagina.locator('#txtObservacao')
        campo.wait_for(state='attached', timeout=timeout_ms)
        return campo

    campo = abrir()
    anterior = campo.input_value().strip()
    novo = limpar_observacao(anterior, catalogo) if catalogo is not None else anterior
    if texto and texto not in novo:
        novo = (novo + '\n' + texto).strip()
    geral = pagina.locator('#txtObservacaoGeral')
    alterar_geral = limpar_geral and geral.count() and bool(geral.input_value().strip())
    if novo != anterior or alterar_geral:
        campo.fill(novo)
        if alterar_geral:
            geral.fill('')
        salvar = pagina.get_by_role('button', name=re.compile(r'^(Alterar|Salvar)$', re.I))
        if salvar.count() != 1:
            raise RuntimeError('Botao para salvar observacoes nao identificado no GEMUL.')
        with pagina.expect_navigation(wait_until='domcontentloaded', timeout=timeout_ms):
            salvar.click()
    campo = abrir()
    if campo.input_value().strip().replace('\r\n', '\n') != novo.replace('\r\n', '\n'):
        raise RuntimeError('As observacoes nao foram confirmadas no GEMUL.')
    if limpar_geral and geral.count() and geral.input_value().strip():
        raise RuntimeError('A remocao da observacao geral nao foi confirmada no GEMUL.')
