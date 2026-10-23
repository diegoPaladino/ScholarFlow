"""Checks against the daily register before manual transfer regularization."""
from student_sync import normalizar

TRANSFER_URL = "https://gemul-aparecida.com.br/app/sca_troca_situacao_aluno_novo.asp"


def situacoes(registros, matricula, nome=""):
    return {normalizar(registro.get("situacao", "")) or "NAO INFORMADA"
            for registro in registros if registro.get("matricula") == matricula
            and (not nome or normalizar(registro.get("nome_aluno", "")) == normalizar(nome))}


def esta_transferido(registros, matricula, nome=""):
    return situacoes(registros, matricula, nome) == {"TRANSFERIDO"}


def esta_ativo(registros, matricula, nome=""):
    return "ATIVO" in situacoes(registros, matricula, nome)


def exigir_transferido(registros, matricula, nome="", *, permitir_ativo=False):
    """Only active students require an explicit confirmation to proceed."""
    if esta_ativo(registros, matricula, nome) and not permitir_ativo:
        raise ValueError("Aluno ATIVO. Confirme a situação antes de continuar o lançamento.")


def abrir_pagina(pagina):
    nova = pagina.context.new_page()
    try:
        nova.goto(TRANSFER_URL, wait_until="domcontentloaded", timeout=60000)
        nova.bring_to_front()
        return nova
    except Exception:
        try:
            nova.close()
        except Exception:
            pass
        raise
