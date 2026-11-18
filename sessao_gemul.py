"""Bounded authentication recovery for GEMUL operations."""
from urllib.parse import urlsplit


progresso = None


def informar_progresso(mensagem):
    if progresso is not None:
        progresso(mensagem)


class SessaoExpirada(RuntimeError):
    pass


class FalhaAutenticacao(RuntimeError):
    pass


def sessao_expirada(pagina):
    try:
        if pagina is None or pagina.is_closed():
            return False
        caminho = urlsplit(pagina.url).path.lower()
        if caminho.endswith('/login.asp') or caminho.endswith('/default.asp') or caminho.startswith('/login/'):
            return True
        return pagina.locator('#txtLogin').is_visible()
    except Exception:
        # An unavailable browser is not evidence of logout and must not trigger a replay.
        return False


def exigir_sessao(pagina):
    if pagina is None or pagina.is_closed():
        raise RuntimeError('O navegador foi fechado antes de concluir o procedimento.')
    if sessao_expirada(pagina):
        raise SessaoExpirada('O acesso ao GEMUL expirou durante o procedimento.')


def abrir_historico_autenticado(pagina, url, autenticar, abrir_menu, progresso):
    """Probe the server, including when the old DOM still looks authenticated."""
    progresso('Conferindo o acesso ao GEMUL...')
    pagina.goto(url, wait_until='domcontentloaded', timeout=30000)
    if sessao_expirada(pagina):
        progresso('O acesso expirou. Entrando novamente no GEMUL...')
        try:
            autenticar(pagina)
            abrir_menu(pagina, apos_login=True)
        except Exception as exc:
            raise FalhaAutenticacao(f'Não foi possível recuperar o acesso: {exc}') from exc
        pagina.goto(url, wait_until='domcontentloaded', timeout=30000)
    exigir_sessao(pagina)
    pagina.locator('#txtMatricula').wait_for(state='visible', timeout=15000)


def executar_com_recuperacao(acao, obter_pagina, recuperar, progresso):
    """Retry once, only with evidence of logout; callers must support resumption."""
    for tentativa in range(2):
        try:
            resultado = acao()
            exigir_sessao(obter_pagina())
            return resultado
        except Exception as exc:
            if isinstance(exc, FalhaAutenticacao):
                raise
            expirou = isinstance(exc, SessaoExpirada) or sessao_expirada(obter_pagina())
            if not expirou:
                raise
            if tentativa:
                raise SessaoExpirada(
                    'O GEMUL encerrou o acesso novamente. O procedimento foi interrompido; '
                    'confira o acesso e tente novamente. Os dados do formulário foram preservados.'
                ) from exc
            progresso('O acesso expirou. Recuperando o login para retomar o procedimento...')
            recuperar()
