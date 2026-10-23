"""Phone selection and browser handoff for school-record requests."""
import json
import os
from pathlib import Path
import re
import tempfile

TELEFONES = {
    "telefone_celular": "Celular", "telefone_comercial": "Comercial",
    "telefone_residencial": "Residencial", "telefone_responsavel": "Responsável",
}
DDDS = set("11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 91 92 93 94 95 96 97 98 99".split())


def salvar_textos_padrao(texto_responsaveis, texto_institucional, destino=None, registros=None):
    """Replace the developer preview with the current student's two messages."""
    path = Path(destino) if destino is not None else Path(
        r"C:\Users\Public\textos_padrao_cobranca_historico.txt")
    lista_contatos = contatos(registros or [])
    telefones = "CONTATOS CADASTRADOS DO ALUNO\n" + (
        "\n".join(f"{', '.join(contato['origens'])}: https://wa.me/{contato['numero']}"
                  for contato in lista_contatos)
        if lista_contatos else "Nenhum telefone com DDD valido encontrado."
    )
    conteudo = (
        "TEXTOS PADRÃO - COBRANÇA DE HISTÓRICO ESCOLAR\n\n"
        f"{telefones}\n\n"
        f"1) RESPONSÁVEIS / WHATSAPP\n\n{texto_responsaveis}\n\n"
        + "=" * 65 + "\n\n"
        f"2) INSTITUIÇÃO ANTERIOR / E-MAIL\n\n{texto_institucional}\n"
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", dir=path.parent,
                                         suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(conteudo)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def contatos(registros):
    encontrados = {}
    pattern = r"(?<!\d)(?:\+?55[\s.-]*)?\(?([1-9]\d)\)?[\s.-]*(\d{4,5})[\s.-]*(\d{4})(?!\d)"
    for registro in registros:
        for campo, rotulo in TELEFONES.items():
            for match in re.finditer(pattern, str(registro.get(campo) or "")):
                ddd, inicio, fim = match.groups()
                if ddd not in DDDS or (len(inicio) == 5 and not inicio.startswith("9")):
                    continue
                numero = "55" + ddd + inicio + fim
                contato = encontrados.setdefault(numero, {"numero": numero,
                    "exibicao": f"({ddd}) {inicio}-{fim}", "origens": []})
                if rotulo not in contato["origens"]:
                    contato["origens"].append(rotulo)
    return list(encontrados.values())


def carregar_utilizados(base_dir, matricula):
    path = Path(base_dir) / "cobranca_contatos_utilizados.json"
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get(matricula, []))


def marcar_utilizado(base_dir, matricula, numero):
    path = Path(base_dir) / "cobranca_contatos_utilizados.json"
    dados = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    dados[matricula] = sorted(set(dados.get(matricula, [])) | {numero})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=base_dir,
                                         suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump(dados, file)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def abrir_conversa(numero, texto, posicao, automacao, clipboard):
    if not re.fullmatch(r"55\d{10,11}", numero):
        raise ValueError("Telefone inválido para abrir o WhatsApp.")
    if any(type(posicao.get(chave)) is not int for chave in ("x", "y")):
        raise ValueError("Capture novamente a posição do navegador ao iniciar o programa.")
    try:
        automacao.click(posicao["x"], posicao["y"])
        automacao.sleep(0.4)
        automacao.hotkey("ctrl", "t")
        automacao.sleep(0.4)
        clipboard.copy("https://wa.me/" + numero)
        automacao.hotkey("ctrl", "v")
        automacao.sleep(0.2)
        automacao.press("enter")
    finally:
        clipboard.copy(texto)
