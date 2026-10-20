# Bibliotecas
# -*- coding: utf-8 -*-
import time
import credenciais_locais
import whatsapp_posicao
from student_sync import atualizar_base_diaria, base_atualizada_hoje, verificar_espaco
from datetime import datetime
import json
import base64
import socket
import ssl
import urllib.request
import urllib.error
import sys
import threading
import traceback
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import pyautogui as p
import clipboard as c
import pyperclip as pp
import tkinter as tk
from tkinter import simpledialog, ttk, filedialog, messagebox
import os
import tempfile
import winsound
import hashlib
from PIL import Image, ImageTk

def _int_env(nome: str, padrao: int) -> int:
    try:
        return int(str(os.getenv(nome, "") or "").strip() or padrao)
    except (TypeError, ValueError):
        return padrao


LOG_FILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "HistoricoAutomatizado.log",
)
GEMUL_BASE_URL = "https://gemul-aparecida.com.br"
GEMUL_LOGIN_URL = f"{GEMUL_BASE_URL}/login.asp"
GEMUL_HISTORICO_URL = f"{GEMUL_BASE_URL}/app/sca_historico_escolar_novoCon.asp"
AUTO_HISTORICO_DIR = r"C:\Users\Public\001_historicos"
LLM_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".pdf", ".txt"}
OCR_IA_TIMEOUT_SEGUNDOS = 180
OCR_IA_TENTATIVAS = 2
OCR_IA_REASONING_EFFORT = "low"
OCR_IA_MODEL_PADRAO = (os.getenv("OPENAI_OCR_MODEL") or "gpt-5-mini").strip() or "gpt-5-mini"
OCR_IA_MAX_IMAGE_SIDE = _int_env("OCR_IA_MAX_IMAGE_SIDE", 1200)
OCR_IA_JPEG_QUALITY = _int_env("OCR_IA_JPEG_QUALITY", 82)
MARCADORES_TEXTO_CORROMPIDO = ("Ã", "Â", "â", "ð", "�")
ESCOLA_PADRAO = "ESCOLA MUNICIPAL JARDIM BELA VISTA"
CIDADE_ESCOLA_PADRAO = "APARECIDA DE GOIÂNIA"
UF_ESCOLA_PADRAO = "GO"
ESCOLAS_SUGERIDAS = [
    ESCOLA_PADRAO,
]


def _decodificar_texto_mojibake_misto(texto: str) -> str:
    bruto = bytearray()
    for caractere in texto:
        try:
            bruto.extend(caractere.encode("cp1252"))
            continue
        except UnicodeEncodeError:
            pass
        try:
            bruto.extend(caractere.encode("latin-1"))
        except UnicodeEncodeError as exc:
            raise UnicodeDecodeError("utf-8", bytes(bruto), len(bruto), len(bruto) + 1, str(exc)) from exc
    return bytes(bruto).decode("utf-8")


def maximizar_janela_tk(janela: tk.Misc) -> None:
    def aplicar_maximizacao() -> None:
        try:
            janela.state("zoomed")
            return
        except Exception:
            pass
        try:
            janela.attributes("-zoomed", True)
            return
        except Exception:
            pass
        try:
            largura = janela.winfo_screenwidth()
            altura = janela.winfo_screenheight()
            janela.geometry(f"{largura}x{altura}+0+0")
        except Exception:
            pass

    try:
        janela.update_idletasks()
    except Exception:
        pass

    aplicar_maximizacao()

    try:
        if not getattr(janela, "_maximizacao_automatica_configurada", False):
            janela.bind("<Map>", lambda _evento: janela.after(10, aplicar_maximizacao), add="+")
            setattr(janela, "_maximizacao_automatica_configurada", True)
        janela.after(50, aplicar_maximizacao)
        janela.after(250, aplicar_maximizacao)
    except Exception:
        pass


def reparar_acentos_mistos(texto: str) -> str:
    """Decode UTF-8 byte sequences stored as Latin-1/Windows-1252 characters."""
    def byte_caractere(caractere):
        for encoding in ("cp1252", "latin-1"):
            try:
                return caractere.encode(encoding)[0]
            except UnicodeEncodeError:
                continue
        return None

    for _ in range(3):
        resultado = []
        indice = 0
        alterado = False
        while indice < len(texto):
            primeiro = byte_caractere(texto[indice])
            tamanho = (2 if primeiro is not None and 0xC2 <= primeiro <= 0xDF else
                       3 if primeiro is not None and 0xE0 <= primeiro <= 0xEF else
                       4 if primeiro is not None and 0xF0 <= primeiro <= 0xF4 else 0)
            trecho = texto[indice:indice + tamanho] if tamanho else ""
            valores = [byte_caractere(c) for c in trecho]
            if tamanho and len(valores) == tamanho and all(v is not None for v in valores):
                try:
                    corrigido = bytes(valores).decode("utf-8")
                except UnicodeDecodeError:
                    pass
                else:
                    resultado.append(corrigido)
                    indice += tamanho
                    alterado = True
                    continue
            resultado.append(texto[indice])
            indice += 1
        texto = "".join(resultado)
        if not alterado:
            break
    return texto


def corrigir_texto_utf8(valor) -> str:
    texto = "" if valor is None else str(valor)
    if not texto:
        return ""

    texto = reparar_acentos_mistos(texto.replace("\ufeff", ""))
    for _ in range(2):
        if not any(marcador in texto for marcador in MARCADORES_TEXTO_CORROMPIDO):
            break

        reparado = None
        for tentativa in (
            lambda valor_atual: valor_atual.encode("latin-1").decode("utf-8"),
            lambda valor_atual: valor_atual.encode("cp1252").decode("utf-8"),
            _decodificar_texto_mojibake_misto,
        ):
            try:
                candidato = tentativa(texto)
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if candidato and candidato != texto:
                reparado = candidato
                break

        if reparado is None:
            break
        texto = reparado

    substituicoes_residuais = {
        "HistÃ³rico": "Histórico",
        "histÃ³rico": "histórico",
        "ResoluÃ§Ã£o": "Resolução",
        "resoluÃ§Ã£o": "resolução",
        "observaÃ§Ã£o": "observação",
        "ObservaÃ§Ã£o": "Observação",
        "GoiÃ¢nia": "Goiânia",
        "goiÃ¢nia": "goiânia",
        "nÂº": "nº",
        "NÂº": "Nº",
    }
    for origem, destino in substituicoes_residuais.items():
        texto = texto.replace(origem, destino)

    return texto


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass
        return len(data)

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self):
        return False


_log_stream = open(LOG_FILE_PATH, "a", encoding="utf-8", buffering=1, errors="replace")
_log_stream.write(f"\n===== Execucao iniciada em {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
sys.stdout = TeeStream(sys.__stdout__, _log_stream)
sys.stderr = TeeStream(sys.__stderr__, _log_stream)


def encerrar_processo_imediatamente(codigo: int = 0) -> None:
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.flush()
    except Exception:
        pass
    try:
        _log_stream.flush()
        _log_stream.close()
    except Exception:
        pass
    os._exit(codigo)

# InÃ­cio da contagem do tempo
start_time = time.time()  # InÃ­cio do cronÃ´metro
print("Execucao iniciada em:", datetime.now())
print("Log do programa:", LOG_FILE_PATH)

# Estado Playwright (substitui WebDriver do Selenium)
play = None
browser = None
context = None
driver = None  # manter o nome por compatibilidade: Ã© um Page do Playwright
seletor = None
sessao_execucao = {
    "matricula_atual": "",
    "navegador_inicializado": False,
    "resolucao_011_completa_por_matricula": set(),
}


from playwright.sync_api import Error as PlaywrightError, Locator
from typing import Any, Optional, Dict, List, Tuple
import re
import unicodedata
import csv
import difflib


def solicitar_credenciais_gemul():
    try:
        salvas = credenciais_locais.carregar()
    except Exception:
        salvas = {}
        messagebox.showwarning("Credenciais", "Não foi possível ler as credenciais salvas. Informe-as novamente.")

    class LoginDialog(simpledialog.Dialog):
        def body(self, master):
            self.usuario = tk.StringVar(value=os.getenv('GEMUL_USERNAME') or salvas.get('usuario', ''))
            self.senha = tk.StringVar(value=os.getenv('GEMUL_PASSWORD') or salvas.get('senha', ''))
            self.lembrar = tk.BooleanVar(value=bool(salvas))
            ttk.Label(master, text="Usuário:").grid(row=0, column=0, sticky='w')
            entrada = ttk.Entry(master, textvariable=self.usuario, width=32)
            entrada.grid(row=0, column=1, padx=8, pady=5)
            ttk.Label(master, text="Senha:").grid(row=1, column=0, sticky='w')
            ttk.Entry(master, textvariable=self.senha, show='*', width=32).grid(row=1, column=1, padx=8, pady=5)
            ttk.Checkbutton(master, text="Lembrar credenciais neste Windows", variable=self.lembrar).grid(row=2, columnspan=2, pady=8)
            ttk.Label(master, text="Desmarque para apagar as credenciais memorizadas.").grid(row=3, columnspan=2)
            return entrada

        def validate(self):
            if not self.usuario.get().strip() or not self.senha.get():
                messagebox.showwarning('GEMUL', 'Informe usuário e senha.', parent=self)
                return False
            return True

        def apply(self):
            self.result = (self.usuario.get().strip(), self.senha.get(), self.lembrar.get())

    dialogo = LoginDialog(tk._default_root, title='Acesso ao GEMUL')
    if not dialogo.result:
        raise RuntimeError('Login cancelado.')
    login, senha, lembrar = dialogo.result
    if not lembrar:
        credenciais_locais.esquecer()
    return login, senha, lembrar


def gerar_texto_cobranca_historico(dados):
    nome = str(dados.get('nome_aluno', '')).strip()
    matricula = re.sub(r'\D', '', str(dados.get('numero_matricula', '')))
    if not nome or len(matricula) != 9:
        raise ValueError('Informe o nome do aluno e uma matrícula válida para gerar a cobrança.')
    escola = str(dados.get('nome_escola', '')).strip() or ESCOLA_PADRAO
    return (
        f"Olá! Falta entregar o histórico escolar de {nome} (matrícula {matricula}).\n\n"
        f"Peça esse documento na escola anterior e entregue na secretaria da {escola}.\n\n"
        f"Se já entregou, avise a secretaria. Obrigado!"
    )


def registrar_etapa_historico(etapa, pagina=None, **detalhes):
    evento = {"data_hora": datetime.now().astimezone().isoformat(), "etapa": etapa,
              "url": getattr(pagina, "url", ""), **detalhes}
    print("HISTORICO " + json.dumps(evento, ensure_ascii=False, default=str))


def indice_registro_historico(linhas, ano, serie, escola):
    candidatos = []
    for indice, celulas in enumerate(linhas):
        if len(celulas) < 5:
            continue
        if (str(celulas[0]).strip() == str(ano)
                and normalizar_serie(celulas[4]) == normalizar_serie(serie)
                and normalizar_texto_busca(celulas[2]) == normalizar_texto_busca(escola)):
            candidatos.append(indice)
    if len(candidatos) > 1:
        raise RuntimeError("Mais de um registro corresponde ao ano, serie e escola. Confira os registros no GEMUL.")
    return candidatos[0] if candidatos else None


def abrir_disciplinas_registro(pagina, ano, serie, escola, obrigatorio=True, timeout_ms=15000):
    pagina.wait_for_load_state("domcontentloaded")
    linhas = pagina.locator('tr').filter(has=pagina.locator('button[onclick*="editarDisciplinas"]'))
    dados = linhas.evaluate_all("rows => rows.map(row => Array.from(row.cells).map(cell => cell.innerText.trim()))")
    indice = indice_registro_historico(dados, ano, serie, escola)
    registrar_etapa_historico("selecionar_registro", pagina, ano=ano, serie=serie,
                             escola=escola, registros=dados, indice=indice)
    if indice is None:
        if obrigatorio:
            raise RuntimeError(f"Registro de {ano}, {serie}, {escola} nao encontrado na lista de estudos realizados.")
        return False
    botao = linhas.nth(indice).get_by_role("button", name="Editar Disciplinas", exact=True)
    botao.scroll_into_view_if_needed(timeout=timeout_ms)
    botao.click(timeout=timeout_ms)
    pagina.locator('#cmbDisciplina').wait_for(state="visible", timeout=timeout_ms)
    registrar_etapa_historico("disciplinas_abertas", pagina, ano=ano, serie=serie)
    return True


class By:
    XPATH = "xpath"
    CSS_SELECTOR = "css"
    ID = "id"
    NAME = "name"


class Keys:
    RETURN = "Enter"


class TimeoutException(Exception):
    pass


class NoSuchElementException(Exception):
    pass


class StaleElementReferenceException(Exception):
    pass


class ElementClickInterceptedException(Exception):
    pass


class NoAlertPresentException(Exception):
    pass


class UnexpectedAlertPresentException(Exception):
    pass


def _normalize_selector(by: str, value: str) -> str:
    if by == By.XPATH:
        return f"xpath={value}"
    if by == By.ID:
        return f"#{value}"
    if by == By.NAME:
        return f"[name=\"{value}\"]"
    return value


def _get_base(subject: Any):
    if isinstance(subject, DriverAdapter):
        return subject.page
    if isinstance(subject, ElementAdapter):
        return subject.locator
    return subject


def _build_locator(subject: Any, by: str, selector: str):
    base = _get_base(subject)
    normalized = _normalize_selector(by, selector)
    locator = base.locator(normalized)
    return locator.first


def _normalizar_rotulo_interface(texto: Any) -> str:
    valor = corrigir_texto_utf8(texto).strip()
    if not valor:
        return ""
    valor = (
        valor
        .replace("Âº", "º")
        .replace("Ã‚Âº", "º")
        .replace("°", "º")
        .replace("Âª", "A")
        .replace("ª", "A")
    )
    return normalizar_texto_busca(valor)


def _garantir_locator_visivel(subject: Any, locator: Locator, timeout_ms: int = 10000) -> None:
    pagina = _get_base(subject)
    locator.wait_for(state="attached", timeout=timeout_ms)
    for _ in range(6):
        try:
            locator.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass
        try:
            locator.wait_for(state="visible", timeout=1500)
            return
        except PlaywrightTimeoutError:
            pass
        try:
            pagina.mouse.wheel(0, 900)
        except Exception:
            pass
        try:
            pagina.keyboard.press("PageDown")
        except Exception:
            pass
        try:
            pagina.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)
    locator.wait_for(state="visible", timeout=timeout_ms)


def _pagedown_resgate(subject: Any, vezes: int = 1, pausa_ms: int = 250) -> None:
    pagina = _get_base(subject)
    if pagina is None:
        return
    for _ in range(max(1, vezes)):
        try:
            pagina.keyboard.press("PageDown")
        except Exception:
            try:
                pagina.mouse.wheel(0, 900)
            except Exception:
                pass
        try:
            pagina.wait_for_timeout(pausa_ms)
        except Exception:
            time.sleep(pausa_ms / 1000)


PAGINAS_DIALOGO_AUTO_CONFIGURADAS = set()


def _aceitar_dialogo_automaticamente(dialog: Any) -> None:
    try:
        dialog.accept()
    except PlaywrightError as exc:
        mensagem = str(exc).lower()
        if "already handled" in mensagem or "target page" in mensagem or "has been closed" in mensagem:
            return
        print(f"Falha ao aceitar dialogo automaticamente: {exc}")
    except Exception as exc:
        print(f"Falha inesperada ao aceitar dialogo automaticamente: {exc}")


def configurar_dialogos_automaticos(pagina: Any) -> None:
    pagina_base = _get_base(pagina)
    if pagina_base is None:
        return
    identificador = id(pagina_base)
    if identificador in PAGINAS_DIALOGO_AUTO_CONFIGURADAS:
        return
    pagina_base.on("dialog", _aceitar_dialogo_automaticamente)
    PAGINAS_DIALOGO_AUTO_CONFIGURADAS.add(identificador)


def formulario_historico_aberto(subject: Any, timeout_ms: int = 2500) -> bool:
    pagina = _get_base(subject)
    if pagina is None:
        return False
    for seletor in ("#txtAnoHistorico", "#cmbCurso", "#txtEscola"):
        try:
            pagina.locator(seletor).wait_for(state="attached", timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def _selecionar_opcao_por_texto_normalizado(subject: Any, locator: Locator, texto_desejado: str, timeout_ms: int = 10000) -> None:
    texto_norm = _normalizar_rotulo_interface(texto_desejado)
    _garantir_locator_visivel(subject, locator, timeout_ms=timeout_ms)
    opcoes = locator.evaluate(
        """el => Array.from(el.options || []).map(opt => ({
            label: (opt.label || opt.textContent || '').trim(),
            value: String(opt.value || '')
        }))"""
    )
    for opcao in opcoes:
        if _normalizar_rotulo_interface(opcao.get("label", "")) == texto_norm:
            locator.select_option(value=opcao.get("value", ""), force=True)
            return
    disponiveis = ", ".join(str(op.get("label", "")).strip() for op in opcoes if str(op.get("label", "")).strip())
    raise ValueError(f"Opcao '{texto_desejado}' nao encontrada. Disponiveis: {disponiveis}")


class ElementAdapter:
    def __init__(self, locator: Locator):
        self.locator = locator

    def click(self) -> None:
        try:
            self.locator.click()
        except PlaywrightError as exc:
            raise ElementClickInterceptedException(str(exc)) from exc

    def clear(self) -> None:
        try:
            self.locator.fill("")
        except PlaywrightError as exc:
            raise ElementClickInterceptedException(str(exc)) from exc

    def send_keys(self, value: Any) -> None:
        try:
            if value == Keys.RETURN:
                self.locator.press("Enter")
            else:
                self.locator.type(str(value))
        except PlaywrightError as exc:
            raise ElementClickInterceptedException(str(exc)) from exc

    def fill(self, value: Any) -> None:
        try:
            self.locator.fill(str(value))
        except PlaywrightError as exc:
            raise ElementClickInterceptedException(str(exc)) from exc

    def is_selected(self) -> bool:
        try:
            return self.locator.is_checked()
        except PlaywrightError:
            attr = self.locator.get_attribute("checked")
            return attr in (True, "true", "checked")

    def scroll_into_view(self) -> None:
        try:
            self.locator.scroll_into_view_if_needed()
        except PlaywrightError:
            pass

    def find_element(self, by: str, selector: str) -> "ElementAdapter":
        return ElementAdapter(_build_locator(self, by, selector))

    def select_option(self, *, label: str | None = None, value: str | None = None) -> None:

        options = {}
        if label is not None:
            options["label"] = label
        if value is not None:
            options["value"] = value
        self.locator.select_option(**options, force=True)


    def __getattr__(self, name: str):
        return getattr(self.locator, name)


class DriverAdapter:
    def __init__(self, page):
        self.page = page

    def find_element(self, by: str, selector: str) -> ElementAdapter:
        locator = _build_locator(self.page, by, selector)
        if locator.count() == 0:
            raise NoSuchElementException(f"Elemento nao encontrado para seletor {selector}")
        return ElementAdapter(locator)

    def execute_script(self, script: str, *args: Any) -> Any:
        def ensure_element(obj: Any) -> ElementAdapter:
            if isinstance(obj, ElementAdapter):
                return obj
            if isinstance(obj, Locator):
                return ElementAdapter(obj)
            raise ValueError("Argumento nao suportado para execute_script")

        if script.startswith("arguments[0].value = ''"):
            element = ensure_element(args[0])
            element.clear()
            return None
        if script.startswith("arguments[0].value = arguments[1]"):
            element = ensure_element(args[0])
            element.fill(args[1])
            return None
        if "scrollIntoView" in script:
            element = ensure_element(args[0])
            element.scroll_into_view()
            return None
        if "arguments[0].click()" in script:
            element = ensure_element(args[0])
            element.click()
            return None
        if script.startswith("window.open"):
            match = re.search(r"'([^']+)'", script)
            if match:
                url = match.group(1)
                global context
                if context:
                    new_page = context.new_page()
                    new_page.goto(url)
            return None
        raise NotImplementedError(f"Script nao suportado: {script}")

    def wait_for_load_state(self, state: str = "load", timeout: Optional[float] = None) -> None:
        if timeout is None:
            self.page.wait_for_load_state(state=state)
        else:
            self.page.wait_for_load_state(state=state, timeout=timeout)

    def on(self, event: str, handler) -> None:
        self.page.on(event, handler)

    def __getattr__(self, name: str):
        return getattr(self.page, name)


def maximizar_janela_navegador(page: Any) -> None:
    pagina = _get_base(page)
    try:
        pagina.bring_to_front()
    except Exception:
        pass
    try:
        sessao_cdp = pagina.context.new_cdp_session(pagina)
        info_janela = sessao_cdp.send("Browser.getWindowForTarget")
        sessao_cdp.send(
            "Browser.setWindowBounds",
            {
                "windowId": info_janela["windowId"],
                "bounds": {"windowState": "maximized"},
            },
        )
        return
    except Exception:
        pass
    try:
        pagina.evaluate(
            """() => {
                try {
                    window.moveTo(0, 0);
                    window.resizeTo(screen.availWidth, screen.availHeight);
                } catch (e) {}
            }"""
        )
    except Exception:
        pass
    try:
        p.hotkey("win", "up")
    except Exception:
        pass


class Atalho:
    def alerta_sonoro():
        # Toca um som de notificaÃ§Ã£o do Windows (Beep)
        frequency = 1000  # FrequÃªncia do som, em Hertz (1000 Hz = 1 kHz)
        duration = 2000    # DuraÃ§Ã£o do som, em milissegundos
        winsound.Beep(frequency, duration)

        # Outra opÃ§Ã£o Ã© usar um som do sistema, como uma notificaÃ§Ã£o de 'Exclamation'
        winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)

    # FunÃ§Ãµes de automaÃ§Ã£o de teclado e mouse
    def abrir_nova_aba():
        p.keyDown('ctrl')
        time.sleep(0.2)
        p.hotkey('t')
        time.sleep(0.3)
        p.keyUp('ctrl')
        time.sleep(0.2)

    def ctrl_pageup():
        p.keyDown('ctrl')
        time.sleep(0.2)
        p.hotkey('pageup')
        time.sleep(0.3)
        p.keyUp('ctrl')
        time.sleep(0.2)

    def ctrl_pagedown():
        p.keyDown('ctrl')
        time.sleep(0.2)
        p.hotkey('pagedown')
        time.sleep(0.3)
        p.keyUp('ctrl')
        time.sleep(0.2)

    def pageup():
        p.hotkey('pageup')
        time.sleep(0.3)

    def home():
        p.hotkey('home')
        time.sleep(0.3)

    def pagedown():
        p.hotkey('pagedown')
        time.sleep(0.3)

    def procurar():
        p.keyDown('ctrl')
        time.sleep(0.2)
        p.hotkey('f')
        time.sleep(0.3)
        p.keyUp('ctrl')
        time.sleep(0.2)

    def copiar():
        p.keyDown('ctrl')
        time.sleep(0.2)
        p.hotkey('c')
        time.sleep(0.3)
        p.keyUp('ctrl')
        time.sleep(0.2)

    def colar():
        p.keyDown('ctrl')
        time.sleep(0.2)
        p.hotkey('v')
        time.sleep(0.3)
        p.keyUp('ctrl')
        time.sleep(0.2)

    def enter():
        p.press('enter')
        time.sleep(0.3)

    def tab():
        p.press('tab')
        time.sleep(0.3)

    def alt():
        p.press('tab')
        time.sleep(0.3)

    def alt_tab():
        p.keyDown('alt')
        time.sleep(0.2)
        p.hotkey('tab')
        time.sleep(0.3)
        p.keyUp('alt')
        time.sleep(0.2)

    def alt_tab_tab():
        p.keyDown('alt')
        time.sleep(0.2)
        p.hotkey('tab')
        time.sleep(0.2)
        p.hotkey('tab')
        time.sleep(0.3)
        p.keyUp('alt')
        time.sleep(0.2)

    def alt_tab_tab_tab():
        p.keyDown('alt')
        time.sleep(0.2)
        p.hotkey('tab')
        time.sleep(0.2)
        p.hotkey('tab')
        time.sleep(0.2)
        p.hotkey('tab')
        time.sleep(0.3)
        p.keyUp('alt')
        time.sleep(0.2)

    def imprimir():
        p.keyDown('ctrl')
        time.sleep(0.2)
        p.hotkey('p')
        time.sleep(0.3)
        p.keyUp('ctrl')
        time.sleep(0.2)

    def enter():
        p.keyDown('enter')
        time.sleep(0.2)
        p.keyUp('enter')
        time.sleep(0.2)

    def down():
        p.keyDown('down')
        time.sleep(0.2)
        p.keyUp('down')
        time.sleep(0.2)

    def esc():
        p.hotkey('esc')
        time.sleep(0.3)

    def right():
        p.hotkey('right')
        time.sleep(0.2)

    def left():
        p.hotkey('left')
        time.sleep(0.2)

    def up():
        p.hotkey('up')
        time.sleep(0.2)

    def down():
        p.hotkey('down')
        time.sleep(0.2)

    def click():
        p.click()
        time.sleep(0.2)

    def end():
        p.hotkey('end')
        time.sleep(0.2)

class FuncoesDoPrograma:
    # FunÃ§Ãµes especÃ­ficas do programa
    # NOVA VERSÃƒO: Playwright
    def abrir_chrome():
        global play, browser, context, driver
        verificar_espaco(os.path.dirname(os.path.abspath(__file__)))
        play = sync_playwright().start()
        try:
            browser = play.chromium.launch(
                headless=False,
                channel="chrome",
                args=["--start-maximized"],
            )
        except Exception:
            browser = play.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(accept_downloads=True, viewport=None)
        page = context.new_page()
        configurar_dialogos_automaticos(page)
        page.goto(GEMUL_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        maximizar_janela_navegador(page)
        driver = DriverAdapter(page)
        return driver
        return driver

    def logar(driver):
        # SubstituÃ­do por logar_pw (Playwright)
        pass

    def logar_pw(page):
        usuario = page.locator('xpath=//*[@id="txtLogin"]')
        senha = page.locator('xpath=//*[@id="txtSenha"]')
        botao_login = page.locator('xpath=//*[@id="frm"]/button')

        usuario.wait_for(state="visible", timeout=10000)
        login, password, lembrar = solicitar_credenciais_gemul()
        if not login or not password:
            raise RuntimeError("Login cancelado. Informe usuario e senha para continuar.")
        usuario.fill(login)
        senha.fill(password)

        # Clique no botao Acessar
        botao_login.click()
        page.wait_for_load_state("domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        if lembrar and '/app/' in page.url.lower():
            try:
                credenciais_locais.salvar(login, password)
            except Exception:
                messagebox.showwarning('Credenciais', 'O login foi realizado, mas não foi possível memorizar as credenciais.')
        print(f'Login enviado pelo botao "Acessar". URL atual apos login: {page.url}')

    def abrir_novas_abas(driver):
        urls = [
            GEMUL_HISTORICO_URL
        ]
        
        for url in urls:
            driver.execute_script(f"window.open('{url}', '_blank');")
            driver.switch_to.window(driver.window_handles[-1])
        
        # Volta para a primeira aba
        driver.switch_to.window(driver.window_handles[0])

    # VersÃ£o Playwright
    def abrir_novas_abas_pw(page, apos_login=False):
        global driver
        etapas = [
            ("modulo academico", "//div[contains(concat(' ', normalize-space(@class), ' '), ' module-card ') and contains(@onclick, '/app/academico.asp')]"),
            ("menu Manutencao", '//*[@id="js-nav-menu"]/li[4]/a/span'),
            ("Historico Escolar - Lancamento", '//*[@id="js-nav-menu"]/li[4]/ul/li[6]/a/span'),
        ]
        if not apos_login:
            # Recuperacao da tela com uma sessao ja autenticada.
            page.goto(GEMUL_HISTORICO_URL, wait_until="domcontentloaded", timeout=60000)
            etapas = []
        for nome, xpath in etapas:
            try:
                item = page.locator(f"xpath={xpath}")
                item.wait_for(state="visible", timeout=30000)
                item.click(timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=60000)
                print(f"Selecionado: {nome}.")
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(
                    f"Nao foi possivel selecionar {nome} apos o login. "
                    "Verifique se a autenticacao terminou e se o layout do GEMUL mudou."
                ) from exc

        url_atual = page.url.lower()
        print(f"URL recebida apos abrir historico: {page.url}")

        if "/default.asp" in url_atual:
            raise RuntimeError(
                "A requisicao para a tela de historico foi redirecionada para default.asp. "
                "Isso indica que a sessao de login nao foi reconhecida pelo sistema."
            )
        if page.locator('xpath=//*[@id="txtLogin"]').count() > 0:
            raise RuntimeError(
                'A tela de historico redirecionou de volta para o login. '
                'Verifique se o clique em "Acessar" concluiu a autenticacao.'
            )

        # Aguarda o campo de matricula na tela de historico
        page.locator('xpath=//*[@id="txtMatricula"]').wait_for(state="visible", timeout=15000)
        maximizar_janela_navegador(page)
        print("Tela de Historico Escolar carregada com sucesso.")
        driver = page

    def seleciona_segunda_janela(driver):
        global context
        if context and len(context.pages) > 1:
            return DriverAdapter(context.pages[1])
        return driver

    def seleciona_terceira_janela(driver):
        global context
        if context and len(context.pages) > 2:
            return DriverAdapter(context.pages[2])
        return driver

    def seleciona_quarta_janela(driver):
        global context
        if context and len(context.pages) > 3:
            return DriverAdapter(context.pages[3])
        return driver

    def seleciona_quinta_janela(driver):
        global context
        if context and len(context.pages) > 4:
            return DriverAdapter(context.pages[4])
        return driver

    def seleciona_setima_janela(driver):
        global context
        if context and len(context.pages) > 6:
            return DriverAdapter(context.pages[6])
        return driver

    def fechar_elementos_e_alertas_old(driver):
        pass

    def fechar_elementos_e_alertas(driver):
        modal_xpath = '//*[@id="fechar_modal"]'
        try:
            modal = _build_locator(driver, By.XPATH, modal_xpath)
            modal.wait_for(state="visible", timeout=3000)
            modal.scroll_into_view_if_needed()
            modal.click()
            print('Elemento de sobreposicao fechado com sucesso.')
            return True
        except PlaywrightTimeoutError:
            print('Modal nao apareceu dentro do timeout.')
        except (NoSuchElementException, TimeoutException, ElementClickInterceptedException, PlaywrightError) as exc:
            print(f'Nenhum elemento de sobreposicao encontrado ou erro ao fechar: {exc}')

        try:
            driver.wait_for_timeout(2000)
            driver.keyboard.press('Enter')
            print('Enter pressionado para fechar possivel alerta.')
            return True
        except Exception as exc:
            print(f'Falha ao pressionar Enter para fechar alerta: {exc}')
        return False

    def escrever_texto(driver, xpath, texto, timeout_ms=10000):
        attempts = 3
        texto_normalizado = corrigir_texto_utf8(texto)
        while attempts > 0:
            try:
                locator = _build_locator(driver, By.XPATH, xpath)
                _garantir_locator_visivel(driver, locator, timeout_ms=timeout_ms)
                locator.click()
                locator.fill(texto_normalizado)
                return
            except Exception as exc:
                attempts -= 1
                print(f"Tentativa restante: {attempts}")
                if attempts == 0:
                    raise
                time.sleep(0.3)

    def marcar_checkbox(driver, xpath, timeout_ms=10000):
        attempts = 3
        while attempts > 0:
            try:
                locator = _build_locator(driver, By.XPATH, xpath)
                locator.wait_for(state="visible", timeout=timeout_ms)
                locator.scroll_into_view_if_needed()
                if not locator.is_checked():
                    locator.check()
                return
            except Exception as exc:
                attempts -= 1
                print(f"Tentativa restante: {attempts}")
                if attempts == 0:
                    raise
                time.sleep(0.3)

    def _curso_coords_file_path():
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "curso_coords.json")

    def _carregar_coordenadas_curso():
        coords_path = FuncoesDoPrograma._curso_coords_file_path()
        if os.path.exists(coords_path):
            try:
                with open(coords_path, "r", encoding="utf-8") as arquivo:
                    coords = json.load(arquivo)
                if isinstance(coords, dict) and "x" in coords and "y" in coords:
                    print(f"Coordenadas do curso carregadas de {coords_path}: {coords}")
                    return coords
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Falha ao carregar coordenadas do curso ({exc}). Elas serao solicitadas novamente.")
        return None

    def _solicitar_coordenadas_curso():
        p.alert(
            'Clique em OK e, em seguida, voce tera 3 segundos para posicionar o cursor sobre o campo \"Curso\" na pagina.'
        )
        time.sleep(3)
        x, y = p.position()
        coords = {"x": x, "y": y}
        coords_path = FuncoesDoPrograma._curso_coords_file_path()
        try:
            with open(coords_path, "w", encoding="utf-8") as arquivo:
                json.dump(coords, arquivo)
        except OSError as exc:
            print(f"Erro ao salvar as coordenadas do curso: {exc}")
        else:
            print(f"Coordenadas do curso salvas em {coords_path}: {coords}")
        return coords

    def obter_coordenadas_curso():
        coords = FuncoesDoPrograma._carregar_coordenadas_curso()
        if coords:
            return coords
        return FuncoesDoPrograma._solicitar_coordenadas_curso()

    def escrever_ano_na_caixa(driver, ano):
        attempts = 3
        while attempts > 0:
            try:
                campo_ano = driver.locator('#txtAnoHistorico')
                _garantir_locator_visivel(driver, campo_ano, timeout_ms=10000)
                campo_ano.click()
                campo_ano.fill(str(ano))
                campo_ano.press('Tab')
                driver.wait_for_timeout(150)
                driver.keyboard.press('Tab')
                driver.wait_for_load_state('networkidle')
                driver.wait_for_timeout(2000)
                # Aguarda o recarregamento das opÃ§Ãµes do combo de curso
                driver.wait_for_function(
                    "selector => {"
                    "  const select = document.querySelector(selector);"
                    "  return !!select && select.options.length > 1;"
                    "}",
                    arg='#cmbCurso',
                    timeout=10000,
                )
                FuncoesDoPrograma.obter_coordenadas_curso()
                _pagedown_resgate(driver, vezes=1, pausa_ms=250)
                break
            except PlaywrightTimeoutError as e:
                attempts -= 1
                print(f'Tentativa restante: {attempts}')
                if attempts == 0:
                    raise e
            except Exception as e:
                attempts -= 1
                print(f'Tentativa restante: {attempts}')
                if attempts == 0:
                    raise e

    def btn_incluir_start(driver_ref=None):
        pagina = _get_base(driver_ref if driver_ref is not None else driver)
        if pagina is None:
            raise RuntimeError("Nenhuma pagina ativa do navegador foi encontrada para abrir o formulario.")
        incluir_btn = pagina.locator('#btnIncluir')
        if not incluir_btn.count():
            incluir_btn = pagina.get_by_role("button", name="Incluir", exact=True).first
        _garantir_locator_visivel(pagina, incluir_btn, timeout_ms=10000)

        estrategias = (
            ("clique normal", lambda: incluir_btn.click()),
            ("clique forcado", lambda: incluir_btn.click(force=True)),
            (
                "clique via javascript",
                lambda: incluir_btn.evaluate("el => el.click()"),
            ),
        )

        ultimo_erro = None
        for descricao, acao in estrategias:
            try:
                acao()
                pagina.wait_for_timeout(250)
                if formulario_historico_aberto(pagina, timeout_ms=2500):
                    print(f"Botao inicial, para incluir registro de historico, acionado com sucesso ({descricao}).")
                    return
                ultimo_erro = RuntimeError(
                    "O clique no botao Incluir foi executado, mas o formulario nao abriu."
                )
                print(f"{descricao.title()} nao abriu o formulario de historico.")
            except Exception as exc:
                ultimo_erro = exc
                print(f"Falha no {descricao} do botao Incluir: {exc}")

        if ultimo_erro is not None:
            raise ultimo_erro
        raise RuntimeError("Nao foi possivel acionar o botao Incluir.")

    def preparar_formulario_inclusao(driver_ref, ano):
        pagina_atual = _get_base(driver_ref)
        matricula_atual = _normalizar_matricula_gemul(sessao_execucao.get("matricula_atual"))

        for tentativa in range(1, 3):
            try:
                FuncoesDoPrograma.btn_incluir_start(pagina_atual)
                FuncoesDoPrograma.escrever_ano_na_caixa(pagina_atual, ano)
                return pagina_atual
            except Exception as exc:
                print(f"Falha ao preparar formulario do historico (tentativa {tentativa}/2): {exc}")
                if tentativa == 2 or not matricula_atual:
                    raise
                print("Recarregando a tela de historico com a sessao atual para tentar novamente...")
                pagina_atual = garantir_sessao_gemul(matricula_atual, force_reabrir_tela=True)
        return pagina_atual

    def garantir_etapa_disciplinas(driver, timeout_ms=15000):
        pagina = _get_base(driver)
        disciplina = pagina.locator('#cmbDisciplina')
        if disciplina.count():
            disciplina.wait_for(state="visible", timeout=timeout_ms)
            return
        alvo = sessao_execucao.get("historico_alvo", {})
        if "sca_historico_escolar_novocon.asp" in pagina.url.lower():
            abrir_disciplinas_registro(pagina, **alvo, timeout_ms=timeout_ms)
            return
        # The initial history form must be saved before disciplines exist in the DOM.
        if "sca_historico_escolar_novo.asp" not in pagina.url.lower():
            disciplina.wait_for(state="visible", timeout=timeout_ms)
            return
        botao = pagina.get_by_role("button", name="Incluir", exact=True)
        if not botao.count():
            botao = pagina.locator('input[type="submit"][value="Incluir"], input[type="button"][value="Incluir"]')
        botao = botao.first
        botao.wait_for(state="attached", timeout=timeout_ms)
        try:
            botao.scroll_into_view_if_needed(timeout=3000)
        except PlaywrightTimeoutError:
            for _ in range(12):
                pagina.keyboard.press("PageDown")
                pagina.wait_for_timeout(150)
                if botao.is_visible():
                    try:
                        botao.scroll_into_view_if_needed(timeout=1000)
                        break
                    except PlaywrightTimeoutError:
                        continue
        registrar_etapa_historico("salvar_cabecalho", pagina, **alvo)
        botao.click(timeout=timeout_ms)
        pagina.wait_for_load_state("domcontentloaded")
        if "sca_historico_escolar_novocon.asp" in pagina.url.lower():
            abrir_disciplinas_registro(pagina, **alvo, timeout_ms=timeout_ms)
        else:
            disciplina.wait_for(state="visible", timeout=timeout_ms)

    def incluir_enviar_dados(driver): 
        attempts = 3
        while attempts > 0:
            try:
                # Encontra o botÃ£o e rola a pÃ¡gina atÃ© ele estar visÃ­vel
                botao = driver.locator('xpath=//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]')
                botao.scroll_into_view_if_needed()
                botao.click()

                # Handle any alerts after submitting
                FuncoesDoPrograma.fechar_elementos_e_alertas(driver)

                break
            except (ElementClickInterceptedException, StaleElementReferenceException) as e:
                attempts -= 1
                if attempts == 0:
                    raise e


    def seleciona_uf():
        try:
            uf_lancamento = str(sessao_execucao.get("uf_atual", "") or UF_ESCOLA_PADRAO).strip() or UF_ESCOLA_PADRAO
            dropdown = driver.locator('xpath=//*[@id="cmbUFResidencia"]')
            _selecionar_opcao_por_texto_normalizado(driver, dropdown, uf_lancamento, timeout_ms=10000)

            print(f"UF '{uf_lancamento}' selecionada com sucesso.")
        except Exception as e:
            print(f"Erro ao selecionar a UF: {e}")

    def seleciona_uf_pw():
        try:
            uf_lancamento = str(sessao_execucao.get("uf_atual", "") or UF_ESCOLA_PADRAO).strip() or UF_ESCOLA_PADRAO
            dropdown = driver.locator('xpath=//*[@id="cmbUFResidencia"]')
            _selecionar_opcao_por_texto_normalizado(driver, dropdown, uf_lancamento, timeout_ms=10000)

            print(f"UF '{uf_lancamento}' selecionada com sucesso.")
        except Exception as e:
            print(f"Erro ao selecionar a UF (PW): {e}")

    def situacao_aprovado(driver, ano, cursando="nao"):
        try:
            situacao_elemento = driver.locator('xpath=//*[@id="cmbSituacaoPromocao"]')
            opcao = 'Cursando' if normalizar_cursando_por_ano(ano, cursando) == "sim" else 'Aprovado'
            _selecionar_opcao_por_texto_normalizado(driver, situacao_elemento, opcao, timeout_ms=10000)

            print(f"Situacao '{opcao}' selecionada.")
        except Exception as e:
            print(f"Erro ao selecionar a situacao: {e}")

    def marcar_checkbox_omitir_media(driver, xpath, timeout_ms=10000):
        try:
            checkbox = _build_locator(driver, By.XPATH, xpath)
            checkbox.wait_for(state="visible", timeout=timeout_ms)
            checkbox.scroll_into_view_if_needed()
            if not checkbox.is_checked():
                checkbox.check()
            print('Checkbox marcado com sucesso.')
        except Exception as e:
            print(f"Erro ao marcar o checkbox: {e}")

    def clicar_botao_incluir_final(driver, xpath, timeout_ms=10000):
        seletores_xpath = [
            xpath,
            '//*[@id="panel-8"]//button[contains(translate(normalize-space(.),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"), "incluir")]',
            '//button[contains(translate(normalize-space(.),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"), "incluir")]',
        ]

        ultima_excecao = None
        for seletor in filter(None, seletores_xpath):
            locator = _build_locator(driver, By.XPATH, seletor)
            try:
                locator.wait_for(state="attached", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                ultima_excecao = PlaywrightTimeoutError(f"Nenhum elemento encontrado para seletor: {seletor}")
                continue

            for tentativa in range(1, 4):
                try:
                    locator.scroll_into_view_if_needed()
                    try:
                        locator.wait_for(state="visible", timeout=2000)
                    except PlaywrightTimeoutError:
                        driver.mouse.wheel(0, 800)
                        driver.wait_for_timeout(200)
                        driver.keyboard.press("PageDown")
                        driver.wait_for_timeout(200)
                        locator.wait_for(state="visible", timeout=timeout_ms)
                    locator.click(timeout=timeout_ms, force=True)
                    print("Botao clicado com sucesso.")
                    return
                except Exception as e:
                    print(f"Erro ao clicar no botao (tentativa {tentativa}, seletor {seletor}): {e}")
                    ultima_excecao = e
                    if tentativa == 3:
                        break
                    driver.wait_for_timeout(300)

        if ultima_excecao:
            raise ultima_excecao

    def clicar_item_gerado(driver, xpath, timeout_ms=10000):
        try:
            item = _build_locator(driver, By.XPATH, xpath)
            _garantir_locator_visivel(driver, item, timeout_ms=timeout_ms)
            item.click()
            print('Item clicado com sucesso.')
        except Exception as e:
            print(f"Erro ao clicar no item: {e}")

    def finalizar_navegador():
        global play, browser, context, driver, seletor, sessao_execucao
        try:
            if context:
                context.close()
        except Exception:
            pass
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if play:
                play.stop()
        except Exception:
            pass
        play = None
        browser = None
        context = None
        driver = None
        seletor = None
        sessao_execucao["matricula_atual"] = ""
        sessao_execucao["navegador_inicializado"] = False

class SelecionarCurso:
    
    def __init__(self, driver):
        self.driver = driver

    def _selecionar_curso_por_valor(self, value: str, descricao: str) -> None:
        """Tenta selecionar o curso e emite logs detalhados de cada etapa."""
        global driver
        self.driver = driver
        for tentativa in range(1, 4):
            try:
                print(f"[Curso] Tentativa {tentativa} para selecionar '{descricao}' (value={value})")
                seletor = self._clicar_campo_curso()

                seletor.select_option(value=value, force=True)
                try:
                    self.driver.wait_for_load_state('networkidle', timeout=5000)
                except PlaywrightTimeoutError:
                    print("[Curso] Nenhuma navegaÃ§Ã£o detectada apÃ³s select_option.")
                self.driver.wait_for_timeout(300)

                valor_atual = self.driver.eval_on_selector('#cmbCurso', '(el) => el.value')
                print(f"[Curso] Valor apÃ³s select_option: {valor_atual}")
                if valor_atual == value:
                    self._sincronizar_campo_txtcurso(descricao)
                    print(f"[Curso] SeleÃ§Ã£o confirmada via select_option.")
                    return

                self._forcar_selecao_via_js(value, descricao)
                valor_atual = self.driver.eval_on_selector('#cmbCurso', '(el) => el.value')
                print(f"[Curso] Valor apÃ³s fallback JS: {valor_atual}")
                if valor_atual == value:
                    print(f"[Curso] SeleÃ§Ã£o confirmada via fallback JS.")
                    return

                self._selecionar_via_teclado(value)
                valor_atual = self.driver.eval_on_selector('#cmbCurso', '(el) => el.value')
                print(f"[Curso] Valor apÃ³s fallback teclado: {valor_atual}")
                if valor_atual == value:
                    self._sincronizar_campo_txtcurso(descricao)
                    print(f"[Curso] SeleÃ§Ã£o confirmada via teclado.")
                    return

            except PlaywrightError as exc:
                print(f"[Curso] Erro Playwright na tentativa {tentativa}: {exc}")
            except Exception as exc:
                print(f"[Curso] Erro inesperado na tentativa {tentativa}: {exc}")

            self.driver.wait_for_timeout(400)

        raise RuntimeError(f"[Curso] Falha ao selecionar '{descricao}' (value={value}) apÃ³s mÃºltiplas tentativas.")

    def _forcar_selecao_via_js(self, value: str, descricao: str) -> None:
        """ForÃ§a o value do select via JS e dispara eventos esperados."""
        try:
            self.driver.eval_on_selector(
                '#cmbCurso',
                "(select, value) => {"
                "  select.value = value;"
                "  select.dispatchEvent(new Event('input', { bubbles: true }));"
                "  select.dispatchEvent(new Event('change', { bubbles: true }));"
                "}",
                value,
            )
            try:
                self.driver.wait_for_load_state('networkidle', timeout=5000)
            except PlaywrightTimeoutError:
                pass
            self.driver.wait_for_timeout(300)
            self._sincronizar_campo_txtcurso(descricao)
        except PlaywrightError as exc:
            print(f"[Curso] Falha ao forÃ§ar seleÃ§Ã£o via JS: {exc}")

    def _selecionar_via_teclado(self, value: str) -> None:
        """Simula navegaÃ§Ã£o no select usando teclas."""
        deslocamentos = {'427': 1, '80': 2, '943': 3}
        passos = deslocamentos.get(value, 1)
        try:
            seletor = self.driver.locator('#cmbCurso')
            seletor.click(force=True)
            self.driver.wait_for_timeout(150)
            seletor.press('Home')
            for _ in range(passos):
                seletor.press('ArrowDown')
                self.driver.wait_for_timeout(80)
            seletor.press('Enter')
            try:
                self.driver.wait_for_load_state('networkidle', timeout=5000)
            except PlaywrightTimeoutError:
                pass
            self.driver.wait_for_timeout(300)
        except PlaywrightError as exc:
            print(f"[Curso] Falha ao selecionar via teclado: {exc}")

    def _sincronizar_campo_txtcurso(self, descricao: str) -> None:
        """MantÃ©m o campo oculto txtCurso alinhado com o texto do curso."""
        try:
            self.driver.eval_on_selector(
                '#txtCurso',
                "(el, texto) => { if (el) { el.value = texto; } }",
                corrigir_texto_utf8(descricao),
            )
        except PlaywrightError as exc:
            print(f"[Curso] Aviso: nÃ£o foi possÃ­vel sincronizar txtCurso ({exc})")

    def _clicar_campo_curso(self):
        """Garante um clique real no campo antes da seleÃ§Ã£o."""
        seletor = self.driver.locator('#cmbCurso')
        seletor.wait_for(state='visible', timeout=10000)
        seletor.scroll_into_view_if_needed()
        try:
            box = seletor.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                self.driver.mouse.move(x, y)
                self.driver.mouse.click(x, y, button='left')
            else:
                seletor.click(force=True)
        except PlaywrightError as exc:
            print(f"[Curso] Falha ao clicar via mouse, usando click(force=True). Detalhe: {exc}")
            seletor.click(force=True)
        self.driver.wait_for_timeout(150)
        return seletor

    # MÃ©todo para selecionar EI-EDUCAÃ‡ÃƒO INFANTIL
    def curso_EI_EDUCACAO_INFANTIL(self):
        self._selecionar_curso_por_valor('427', 'EI-EDUCAÃ‡ÃƒO INFANTIL')


    def curso_EF_ENSINO_FUNDAMENTAL(self):
        self._selecionar_curso_por_valor('80', 'EF-ENSINO FUNDAMENTAL')


    def periodo_EI_EDUCACAO_INFANTIL(self, agrupamento):
        global driver
        self.driver = driver
        periodo_elemento = self.driver.locator('xpath=//*[@id="cmbPeriodo"]')

        if agrupamento == 4:
            _selecionar_opcao_por_texto_normalizado(self.driver, periodo_elemento, 'AGRUPAMENTO IV', timeout_ms=10000)

        elif agrupamento == 5:
            _selecionar_opcao_por_texto_normalizado(self.driver, periodo_elemento, 'AGRUPAMENTO V', timeout_ms=10000)


    def periodo_EF_ENSINO_FUNDAMENTAL(self, ano):
        global driver
        self.driver = driver
        periodo_elemento = self.driver.locator('xpath=//*[@id="cmbPeriodo"]')

        if ano == 1:
            _selecionar_opcao_por_texto_normalizado(self.driver, periodo_elemento, f'1{ORDINAL_INDICATOR} ANO', timeout_ms=10000)

        elif ano == 2:
            _selecionar_opcao_por_texto_normalizado(self.driver, periodo_elemento, f'2{ORDINAL_INDICATOR} ANO', timeout_ms=10000)

        elif ano == 3:
            _selecionar_opcao_por_texto_normalizado(self.driver, periodo_elemento, f'3{ORDINAL_INDICATOR} ANO', timeout_ms=10000)

        elif ano == 4:
            _selecionar_opcao_por_texto_normalizado(self.driver, periodo_elemento, f'4{ORDINAL_INDICATOR} ANO', timeout_ms=10000)

        elif ano == 5:
            _selecionar_opcao_por_texto_normalizado(self.driver, periodo_elemento, f'5{ORDINAL_INDICATOR} ANO', timeout_ms=10000)


class SelecionaMateria:

    def __init__(self, driver):
        self.driver = driver

    # MÃ©todo para selecionar 1Âº ou 2Âº MOMENTO para EI - EDUCAÃ‡ÃƒO INFANTIL (Agrupamento 4 ou 5)
    def momento_EI_EDUCACAO_INFANTIL(self, momento):
        FuncoesDoPrograma.garantir_etapa_disciplinas(self.driver)
        global driver
        self.driver = driver
        if _normalizar_rotulo_interface(momento) in {
            _normalizar_rotulo_interface(f"1{ORDINAL_INDICATOR} MOMENTO"),
            _normalizar_rotulo_interface(f"2{ORDINAL_INDICATOR} MOMENTO"),
        }:
            disciplina_elemento = self.driver.locator('xpath=//*[@id="cmbDisciplina"]')
            _selecionar_opcao_por_texto_normalizado(self.driver, disciplina_elemento, momento, timeout_ms=10000)


    def disciplina_EF_ENSINO_FUNDAMENTAL(self, disciplina):
        global driver
        self.driver = driver
        disciplinas_validas_norm = {
            _normalizar_rotulo_interface(item) for item in MAPA_NOTAS_INTERFACE
        }
        if _normalizar_rotulo_interface(disciplina) in disciplinas_validas_norm:
            disciplina_elemento = self.driver.locator('xpath=//*[@id="cmbDisciplina"]')
            _selecionar_opcao_por_texto_normalizado(self.driver, disciplina_elemento, disciplina, timeout_ms=10000)


    def processar_disciplina(self, disciplina, nota, cursando, ano, carga_horaria):
        global driver
        self.driver = driver
        if not nota_deve_ser_lancada(nota):
            print(f"Disciplina {disciplina} ignorada porque nao possui nota util para lancar.")
            return False
        self.disciplina_EF_ENSINO_FUNDAMENTAL(disciplina) or print(f'Disciplina {disciplina} selecionada')
        FuncoesDoPrograma.situacao_aprovado(self.driver, ano, cursando) or print('Situacao selecionada')
        FuncoesDoPrograma.escrever_texto(self.driver, '//*[@id="txtCHTotal"]', carga_horaria) or print('Carga horaria escrita')
        FuncoesDoPrograma.escrever_texto(self.driver, '//*[@id="txtMedia"]', nota) or print(f'Nota da materia {disciplina} escrita')
        FuncoesDoPrograma.clicar_botao_incluir_final(self.driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('Botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(self.driver) or print('Janela de alerta fechada')
        return True

    def processar_registro_sem_nota(self, cursando, ano, carga_horaria):
        global driver
        self.driver = driver
        disciplina_referencia = "ARTES"
        print(
            "Nenhuma disciplina com nota util encontrada; "
            "criando registro minimo com omitir media para gravar o ano."
        )
        self.disciplina_EF_ENSINO_FUNDAMENTAL(disciplina_referencia) or print(
            f'Disciplina {disciplina_referencia} selecionada para registro minimo'
        )
        FuncoesDoPrograma.situacao_aprovado(self.driver, ano, cursando) or print('Situacao selecionada')
        FuncoesDoPrograma.escrever_texto(self.driver, '//*[@id="txtCHTotal"]', carga_horaria) or print('Carga horaria escrita')
        FuncoesDoPrograma.escrever_texto(self.driver, '//*[@id="txtMedia"]', '0') or print('Media 0 escrita para registro minimo')
        FuncoesDoPrograma.marcar_checkbox_omitir_media(
            self.driver,
            '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input',
        ) or print('Checkbox Omitir Media marcado para registro minimo')
        FuncoesDoPrograma.clicar_botao_incluir_final(self.driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('Botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(self.driver) or print('Janela de alerta fechada')
        return True


def processar_disciplinas_ou_registro_minimo(
    seletor_materia: SelecionaMateria,
    dados: Dict[str, Any],
    ano: Any,
    carga_horaria: Any,
) -> None:
    FuncoesDoPrograma.garantir_etapa_disciplinas(seletor_materia.driver)
    disciplinas_notas = montar_disciplinas_notas_interface(dados)
    cursando = dados.get("cursando", "nao")
    if disciplinas_notas:
        for disciplina, nota in disciplinas_notas.items():
            seletor_materia.processar_disciplina(disciplina, nota, cursando, ano, carga_horaria)
        return

    seletor_materia.processar_registro_sem_nota(cursando, ano, carga_horaria)


class CalendarioEscolar:
    def __init__(self):
        self.dias_letivos_especificos = {
            '01': [22, 23, 24, 25, 26, 29, 30, 31],  # Janeiro
            '02': [1, 2, 5, 6, 7, 8, 9, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28, 29],  # Fevereiro
            '03': [1, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 25, 26, 27],  # MarÃ§o
            '04': [1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 29, 30],  # Abril
            '05': [2, 3, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 27, 28, 29],  # Maio
            '06': [3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 17, 18, 19, 20, 21, 24, 25, 26, 27, 28],  # Junho
            '07': [], # Julho - acrescido e corrigido por mim, sem ajuda, de forma autodidata.
            '08': [5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30],  # Agosto
            '09': [2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 23, 24, 25, 26, 27, 30],  # Setembro
            '10': [1, 2, 3, 4, 7, 8, 9, 10, 11, 16, 17, 18, 21, 22, 23, 24, 25, 29, 30, 31],  # Outubro
            '11': [1, 4, 6, 7, 8, 11, 12, 13, 18, 19, 20, 21, 22, 25, 26, 27, 28, 29],  # Novembro
            '12': [2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 16, 17, 18, 19]  # Dezembro
        }
        dias_2024 = self.dias_letivos_especificos
        # Fonte: Calendario Escolar 2026.pdf, SME de Aparecida de Goiânia.
        # Resolução CME nº 109/2025, aprovada em 17/11/2025.
        # Inclui as atividades que compõem os totais mensais oficiais (201 dias).
        dias_2026 = {
            '01': [19, 20, 21, 22, 23, 26, 27, 28, 29, 30],
            '02': [2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 19, 20, 23, 24, 25, 26, 27],
            '03': [2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 23, 24, 25, 26, 27, 30, 31],
            '04': [1, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 22, 23, 24, 27, 28, 29, 30],
            '05': [4, 5, 6, 7, 8, 12, 13, 14, 15, 18, 19, 20, 21, 22, 25, 26, 27, 28, 29],
            '06': [1, 2, 3, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 29, 30],
            '07': [31],
            '08': [3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 17, 18, 19, 20, 21, 24, 25, 26, 27, 28, 31],
            '09': [1, 2, 3, 4, 8, 9, 10, 11, 14, 15, 16, 17, 18, 21, 22, 23, 24, 25, 28, 29, 30],
            '10': [1, 2, 5, 6, 7, 8, 9, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30],
            '11': [3, 4, 5, 6, 9, 10, 11, 12, 13, 16, 17, 18, 19, 23, 24, 25, 26, 27, 30],
            '12': [1, 2, 3, 4, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18],
        }
        self.calendarios = {2024: dias_2024, 2026: dias_2026}
        self.dias_letivos_especificos = dias_2026
        self.data_inicio_aulas = datetime(2026, 1, 19)

    def dias_do_ano(self, ano):
        if ano not in self.calendarios:
            raise ValueError(f'Calendário escolar de {ano} não cadastrado. Informe a carga horária manualmente.')
        return self.calendarios[ano]

    def calcular_dias_letivos(self, data_transferencia):
        fim = datetime.strptime(data_transferencia, '%d/%m/%Y')
        return sum(
            datetime(fim.year, int(mes), dia) <= fim
            for mes, dias in self.dias_do_ano(fim.year).items() for dia in dias
        )

DISCIPLINAS_TABELA = [
    "ARTES",
    "CIENCIAS",
    "CULTURA DE INOVACAO E TECNOLOGIAS",
    "EDUCACAO FISICA",
    "ENSINO RELIGIOSO",
    "GEOGRAFIA",
    "HISTORIA",
    "LINGUA PORTUGUESA",
    "MATEMATICA",
]

CHAVES_NOTAS = [
    "nota_arte",
    "nota_ciencias",
    "nota_cultura",
    "nota_educacao_fisica",
    "nota_ensino_religioso",
    "nota_geografia",
    "nota_historia",
    "nota_lingua_portuguesa",
    "nota_matematica",
]

ROTULOS_NOTAS_OBSERVACAO = {
    "nota_arte": "Artes",
    "nota_ciencias": "Ciencias",
    "nota_cultura": "Cultura de Inovacao e Tecnologias",
    "nota_educacao_fisica": "Educacao Fisica",
    "nota_ensino_religioso": "Ensino Religioso",
    "nota_geografia": "Geografia",
    "nota_historia": "Historia",
    "nota_lingua_portuguesa": "Lingua Portuguesa",
    "nota_matematica": "Matematica",
}

SIGLAS_CONCEITO_CONHECIDAS = {
    "HD",
    "HE",
    "MB",
    "MS",
    "NS",
    "AS",
    "SA",
    "PS",
    "RS",
}

SIGLAS_IGNORADAS_COMO_CONCEITO = {
    "AP",
    "APR",
    "RP",
    "REP",
}

ORDINAL_INDICATOR = "\u00ba"
APARECIDA_RESOLUCAO_011_TEXTO_BASE = (
    "Aluno(a) avaliado(a) conforme a Resolu\u00e7\u00e3o CME n\u00ba. 011, de 25 de novembro de 2019, "
    "que estabelece diretrizes e normas para as etapas e modalidades da Educa\u00e7\u00e3o B\u00e1sica e procedimentos "
    "para credenciamento, recredenciamento, autoriza\u00e7\u00e3o e renova\u00e7\u00e3o de funcionamento de institui\u00e7\u00f5es "
    "educacionais do Sistema Municipal de Ensino de Aparecida de Goi\u00e2nia."
)
APARECIDA_RESOLUCAO_011_TEXTO_RESUMO = (
    "Aluno(a) avaliado(a) conforme a Resolu\u00e7\u00e3o CME n\u00ba. 011, de 25 de novembro de 2019."
)
APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO = (
    "Resolu\u00e7\u00e3o CME n\u00ba. 011, de 25 de novembro de 2019, "
    "que estabelece diretrizes e normas para as etapas e modalidades da Educa\u00e7\u00e3o B\u00e1sica e procedimentos "
    "para credenciamento, recredenciamento, autoriza\u00e7\u00e3o e renova\u00e7\u00e3o de funcionamento de institui\u00e7\u00f5es "
    "educacionais do Sistema Municipal de Ensino de Aparecida de Goi\u00e2nia."
)
APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO_RESUMO = (
    "Resolu\u00e7\u00e3o CME n\u00ba. 011, de 25 de novembro de 2019."
)
APARECIDA_REANP_2020_TEXTO_BASE = (
    "Aprovado(a) conforme Resolu\u00e7\u00e3o CME n\u00ba 014, de 01 de outubro de 2020, "
    "que disp\u00f5e sobre a aprova\u00e7\u00e3o autom\u00e1tica dos alunos devidamente matriculados "
    "na Rede Municipal de Ensino de Aparecida de Goi\u00e2nia."
)
APARECIDA_RESOLUCAO_011_TEXTO_CURTO = "Resolu\u00e7\u00e3o 011/2019."
APARECIDA_OBSERVACAO_1O_2O_ANO = (
    " Avalia\u00e7\u00e3o realizada por meio de Ficha Descritiva, sendo atribu\u00edda nota apenas "
    "\u00e0 disciplina de Educa\u00e7\u00e3o F\u00edsica. Segue anexa a respectiva Ficha Descritiva."
)
APARECIDA_OBSERVACAO_AGRUPAMENTO_4_5 = (
    " Avalia\u00e7\u00e3o realizada por meio de Ficha Descritiva. "
    "Segue anexa a respectiva Ficha Descritiva."
)

MAPA_NOTAS_INTERFACE = {
    "ARTES": "nota_arte",
    "CIÊNCIAS": "nota_ciencias",
    "CULTURA DE INOVAÇÃO E TECNOLOGIAS": "nota_cultura",
    "EDUCAÇÃO FÍSICA": "nota_educacao_fisica",
    "ENSINO RELIGIOSO": "nota_ensino_religioso",
    "GEOGRAFIA": "nota_geografia",
    "HISTÓRIA": "nota_historia",
    "LÍNGUA PORTUGUESA": "nota_lingua_portuguesa",
    "MATEMÁTICA": "nota_matematica",
}


def nota_deve_ser_lancada(valor: Any) -> bool:
    nota = str(valor or "").strip()
    if not nota:
        return False

    nota_norm = normalizar_texto_busca(nota)
    if nota_norm in {
        "-",
        "--",
        "---",
        "----",
        "N/A",
        "NA",
        "SEM NOTA",
        "VAZIO",
        "NADA",
        "NULL",
        "NONE",
    }:
        return False

    nota_numero = nota.replace(",", ".")
    if re.fullmatch(r"0+(?:\.0+)?", nota_numero):
        return False

    return True


def montar_disciplinas_notas_interface(dados: Dict[str, Any]) -> Dict[str, Any]:
    disciplinas_notas: Dict[str, Any] = {}
    for disciplina, chave_nota in MAPA_NOTAS_INTERFACE.items():
        nota = dados.get(chave_nota, "")
        if nota_deve_ser_lancada(nota):
            disciplinas_notas[disciplina] = nota
        else:
            print(f"Disciplina {disciplina} sem nota util; lancamento dispensado.")
    return disciplinas_notas

DISCIPLINA_EQUIVALENCIAS = {
    "ARTE": "nota_arte",
    "ARTES": "nota_arte",
    "CIENCIA": "nota_ciencias",
    "CIENCIAS": "nota_ciencias",
    "CIENCIAS DA NATUREZA": "nota_ciencias",
    "NATUREZA E SOCIEDADE": "nota_ciencias",
    "CULTURA DE INOVACAO E TECNOLOGIAS": "nota_cultura",
    "INOVACAO E TECNOLOGIAS": "nota_cultura",
    "EDUCACAO FISICA": "nota_educacao_fisica",
    "ENSINO RELIGIOSO": "nota_ensino_religioso",
    "GEOGRAFIA": "nota_geografia",
    "HISTORIA": "nota_historia",
    "LINGUA PORTUGUESA": "nota_lingua_portuguesa",
    "PORTUGUES": "nota_lingua_portuguesa",
    "MATEMATICA": "nota_matematica",
}

HISTORICO_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "numero_matricula": {"type": "string"},
        "nome_aluno": {"type": "string"},
        "ano": {"type": "string"},
        "nome_escola": {"type": "string"},
        "cidade": {"type": "string"},
        "uf": {"type": "string"},
        "serie": {"type": "string"},
        "carga_horaria": {"type": "string"},
        "txt_observacoes": {"type": "string"},
        "txt_observacoes_gerais": {"type": "string"},
        "nota_arte": {"type": "string"},
        "nota_ciencias": {"type": "string"},
        "nota_cultura": {"type": "string"},
        "nota_educacao_fisica": {"type": "string"},
        "nota_ensino_religioso": {"type": "string"},
        "nota_geografia": {"type": "string"},
        "nota_historia": {"type": "string"},
        "nota_lingua_portuguesa": {"type": "string"},
        "nota_matematica": {"type": "string"},
        "disciplinas_extra": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "disciplina": {"type": "string"},
                    "nota": {"type": "string"},
                },
                "required": ["disciplina", "nota"],
            },
        },
        "historicos": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ano": {"type": "string"},
                    "serie": {"type": "string"},
                    "nome_escola": {"type": "string"},
                    "cidade": {"type": "string"},
                    "uf": {"type": "string"},
                    "carga_horaria": {"type": "string"},
                    "txt_observacoes": {"type": "string"},
                    "txt_observacoes_gerais": {"type": "string"},
                    "cursando": {"type": "string"},
                    "nota_arte": {"type": "string"},
                    "nota_ciencias": {"type": "string"},
                    "nota_cultura": {"type": "string"},
                    "nota_educacao_fisica": {"type": "string"},
                    "nota_ensino_religioso": {"type": "string"},
                    "nota_geografia": {"type": "string"},
                    "nota_historia": {"type": "string"},
                    "nota_lingua_portuguesa": {"type": "string"},
                    "nota_matematica": {"type": "string"},
                    "disciplinas_extra": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "disciplina": {"type": "string"},
                                "nota": {"type": "string"},
                            },
                            "required": ["disciplina", "nota"],
                        },
                    },
                },
                "required": [
                    "ano",
                    "serie",
                    "nome_escola",
                    "cidade",
                    "uf",
                    "carga_horaria",
                    "txt_observacoes",
                    "txt_observacoes_gerais",
                    "cursando",
                    "nota_arte",
                    "nota_ciencias",
                    "nota_cultura",
                    "nota_educacao_fisica",
                    "nota_ensino_religioso",
                    "nota_geografia",
                    "nota_historia",
                    "nota_lingua_portuguesa",
                    "nota_matematica",
                    "disciplinas_extra",
                ],
            },
        },
    },
    "required": [
        "numero_matricula",
        "nome_aluno",
        "ano",
        "nome_escola",
        "cidade",
        "uf",
        "serie",
        "carga_horaria",
        "txt_observacoes",
        "txt_observacoes_gerais",
        "nota_arte",
        "nota_ciencias",
        "nota_cultura",
        "nota_educacao_fisica",
        "nota_ensino_religioso",
        "nota_geografia",
        "nota_historia",
        "nota_lingua_portuguesa",
        "nota_matematica",
        "disciplinas_extra",
        "historicos",
    ],
}

DOCUMENTO_CIVIL_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "tipo_documento": {"type": "string"},
        "nome_aluno": {"type": "string"},
        "sexo": {"type": "string"},
        "data_nascimento": {"type": "string"},
        "naturalidade": {"type": "string"},
        "pai": {"type": "string"},
        "mae": {"type": "string"},
        "numero_documento": {"type": "string"},
    },
    "required": [
        "tipo_documento",
        "nome_aluno",
        "sexo",
        "data_nascimento",
        "naturalidade",
        "pai",
        "mae",
        "numero_documento",
    ],
}


def normalizar_texto_busca(texto: str) -> str:
    if texto is None:
        return ""
    texto = unicodedata.normalize("NFKD", corrigir_texto_utf8(texto))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.upper()
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def eh_valor_numerico_nota(valor: Any) -> bool:
    texto = str(valor or "").strip()
    if not texto:
        return False
    return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", texto))


def extrair_sigla_conceito(valor: Any) -> str:
    texto = str(valor or "").strip()
    if not texto or eh_valor_numerico_nota(texto):
        return ""

    texto_norm = normalizar_texto_busca(texto)
    texto_norm = re.sub(r"^(CONCEITO|MENCAO|MENCAO FINAL)\s+", "", texto_norm).strip()
    texto_norm = re.sub(r'["\'`]+', "", texto_norm).strip()

    if not re.fullmatch(r"[A-Z]{1,3}", texto_norm):
        return ""
    if texto_norm in SIGLAS_IGNORADAS_COMO_CONCEITO:
        return ""
    return texto_norm


def limpar_nome_disciplina_observacao(nome_disciplina: Any) -> str:
    texto = str(nome_disciplina or "").strip()
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto)


def juntar_lista_materias(materias: List[str]) -> str:
    itens = [str(item).strip() for item in materias if str(item).strip()]
    if not itens:
        return ""
    if len(itens) == 1:
        return itens[0]
    if len(itens) == 2:
        return f"{itens[0]} e {itens[1]}"
    return ", ".join(itens[:-1]) + f" e {itens[-1]}"


def mesclar_textos_observacao(texto_base: str, complemento: str) -> str:
    base = corrigir_texto_utf8(texto_base).strip()
    extra = corrigir_texto_utf8(complemento).strip()
    if not extra or extra in base:
        return base
    if not base:
        return extra
    if base.endswith((".", "!", "?", ";", ":")):
        return f"{base} {extra}"
    return f"{base}. {extra}"


def gerar_observacao_conceitos(conceitos_por_sigla: Dict[str, List[str]]) -> str:
    frases = []
    for sigla, disciplinas in conceitos_por_sigla.items():
        lista_materias = juntar_lista_materias(disciplinas)
        if not lista_materias:
            continue
        if len(disciplinas) == 1:
            frases.append(f'Aluno(a) recebeu o conceito "{sigla}" na materia {lista_materias}.')
        else:
            frases.append(f'Aluno(a) recebeu o conceito "{sigla}" nas materias {lista_materias}.')
    return " ".join(frases).strip()


def converter_conceitos_em_observacoes(registro: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(registro, dict):
        return registro

    candidatos: List[Tuple[str, Any, str, str]] = []
    conceitos_contagem: Dict[str, int] = {}
    notas_numericas = 0

    for chave_nota in CHAVES_NOTAS:
        valor = str(registro.get(chave_nota, "") or "").strip()
        if eh_valor_numerico_nota(valor):
            notas_numericas += 1
            continue
        sigla = extrair_sigla_conceito(valor)
        if not sigla:
            continue
        disciplina = ROTULOS_NOTAS_OBSERVACAO.get(chave_nota, chave_nota)
        candidatos.append(("nota", chave_nota, disciplina, sigla))
        conceitos_contagem[sigla] = conceitos_contagem.get(sigla, 0) + 1

    extras = registro.get("disciplinas_extra", [])
    if isinstance(extras, list):
        for indice, item in enumerate(extras):
            if not isinstance(item, dict):
                continue
            valor = str(item.get("nota", "") or "").strip()
            if eh_valor_numerico_nota(valor):
                continue
            sigla = extrair_sigla_conceito(valor)
            if not sigla:
                continue
            disciplina = limpar_nome_disciplina_observacao(item.get("disciplina", ""))
            if not disciplina:
                continue
            candidatos.append(("extra", indice, disciplina, sigla))
            conceitos_contagem[sigla] = conceitos_contagem.get(sigla, 0) + 1

    if not candidatos:
        return registro

    siglas_unicas = {sigla for _, _, _, sigla in candidatos}
    tem_sigla_conhecida = any(sigla in SIGLAS_CONCEITO_CONHECIDAS for sigla in siglas_unicas)
    repeticao_forte = any(total >= 3 for total in conceitos_contagem.values())
    padrao_predominante = notas_numericas == 0 and len(candidatos) >= 3 and len(siglas_unicas) <= 3

    if not (tem_sigla_conhecida or repeticao_forte or padrao_predominante):
        return registro

    conceitos_por_sigla: Dict[str, List[str]] = {}
    for origem, referencia, disciplina, sigla in candidatos:
        conceitos_por_sigla.setdefault(sigla, [])
        if disciplina not in conceitos_por_sigla[sigla]:
            conceitos_por_sigla[sigla].append(disciplina)

        if origem == "nota":
            registro[referencia] = ""
        elif isinstance(extras, list) and 0 <= referencia < len(extras) and isinstance(extras[referencia], dict):
            extras[referencia]["nota"] = ""

    observacao_conceitos = gerar_observacao_conceitos(conceitos_por_sigla)
    if observacao_conceitos:
        registro["txt_observacoes"] = mesclar_textos_observacao(
            registro.get("txt_observacoes", ""),
            observacao_conceitos,
        )

    return registro


def normalizar_serie(serie_bruta: str) -> str:
    serie_texto = str(serie_bruta or "").strip()
    if not serie_texto:
        return ""
    serie_texto = (
        serie_texto
        .replace("Âº", ORDINAL_INDICATOR)
        .replace("º", ORDINAL_INDICATOR)
        .replace("°", ORDINAL_INDICATOR)
        .replace("Âª", "A")
        .replace("ª", "A")
    )
    serie_norm = normalizar_texto_busca(serie_texto)
    if not serie_norm:
        return ""
    if "AGRUPAMENTO 4" in serie_norm:
        return "AGRUPAMENTO 4"
    if "AGRUPAMENTO 5" in serie_norm:
        return "AGRUPAMENTO 5"
    for numero in ("1", "2", "3", "4", "5"):
        if re.search(rf"\b{numero}\s*(?:O|{ORDINAL_INDICATOR})?\s*ANO\b", serie_norm):
            return f"{numero}{ORDINAL_INDICATOR} ANO"
    return ""


def limpar_nota_extraida(valor: str) -> str:
    nota = str(valor or "").strip()
    if not nota:
        return ""
    nota_norm = normalizar_texto_busca(nota)
    if nota_norm in {"-", "--", "---", "----", "N/A", "NA", "SEM NOTA", "VAZIO", "NADA", "NULL", "NONE"}:
        return ""
    nota_numero = nota.replace(",", ".")
    if re.fullmatch(r"0+(?:\.0+)?", nota_numero):
        return ""
    if re.fullmatch(r"\d+,\d+", nota):
        return nota.replace(",", ".")
    return nota


def mapear_disciplina_para_chave_nota(nome_disciplina: str) -> str:
    nome_norm = normalizar_texto_busca(nome_disciplina)
    if not nome_norm:
        return ""
    if nome_norm in DISCIPLINA_EQUIVALENCIAS:
        return DISCIPLINA_EQUIVALENCIAS[nome_norm]
    for alias, chave_nota in DISCIPLINA_EQUIVALENCIAS.items():
        if alias in nome_norm or nome_norm in alias:
            return chave_nota
    return ""


def aplicar_equivalencias_de_disciplinas(registro_origem: Dict[str, Any], registro_destino: Dict[str, str]) -> None:
    extras = registro_origem.get("disciplinas_extra", [])
    if not isinstance(extras, list):
        return

    for item in extras:
        if not isinstance(item, dict):
            continue
        nome_disciplina = str(item.get("disciplina", "") or "").strip()
        nota = limpar_nota_extraida(item.get("nota", ""))
        if not nome_disciplina or not nota:
            continue
        chave_nota = mapear_disciplina_para_chave_nota(nome_disciplina)
        if chave_nota and not registro_destino.get(chave_nota):
            registro_destino[chave_nota] = nota


def extrair_ano_4_digitos(valor: Any) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    match = re.search(r"\b(19|20)\d{2}\b", texto)
    if match:
        return match.group(0)
    if re.fullmatch(r"\d{4}", texto):
        return texto
    return ""


def exigir_ano_4_digitos(valor: Any) -> str:
    ano = extrair_ano_4_digitos(valor)
    if not ano:
        raise ValueError("Informe o ano do historico com 4 digitos antes de lancar.")
    return ano


def normalizar_sim_nao(valor: Any) -> str:
    texto = normalizar_texto_busca(str(valor or ""))
    if texto in {"SIM", "S", "TRUE", "1", "CURSANDO"}:
        return "sim"
    return "nao"


def normalizar_cursando_por_ano(ano: Any, valor: Any) -> str:
    ano_ref = extrair_ano_4_digitos(ano)
    valor_norm = normalizar_sim_nao(valor)
    if ano_ref and ano_ref != str(datetime.now().year):
        return "nao"
    return valor_norm


def localizar_diretorio_cache_historicos() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "cache_historicos_ocr")


def localizar_diretorio_cache_ocr_arquivos() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "cache_ocr_arquivos")


def localizar_diretorio_cache_formularios() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "cache_formularios_matricula")


def obter_caminho_cache_historico(matricula: str) -> str:
    matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
    if len(matricula_norm) != 9:
        return ""
    return os.path.join(localizar_diretorio_cache_historicos(), f"{matricula_norm}.json")


def salvar_cache_historico_por_matricula(
    matricula: str,
    resultado_ia: Dict[str, Any],
    arquivos_scan: Optional[List[str]] = None,
) -> bool:
    matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
    if len(matricula_norm) != 9 or not isinstance(resultado_ia, dict) or not resultado_ia:
        return False

    os.makedirs(localizar_diretorio_cache_historicos(), exist_ok=True)
    payload = {
        "matricula": matricula_norm,
        "salvo_em": datetime.now().isoformat(timespec="seconds"),
        "arquivos_scan": [str(c).strip() for c in (arquivos_scan or []) if str(c).strip()],
        "resultado_ia": resultado_ia,
    }
    caminho_cache = obter_caminho_cache_historico(matricula_norm)
    if not caminho_cache:
        return False
    with open(caminho_cache, "w", encoding="utf-8") as arquivo:
        json.dump(payload, arquivo, ensure_ascii=False, indent=2)
    return True


def carregar_cache_historico_por_matricula(matricula: str) -> Optional[Dict[str, Any]]:
    caminho_cache = obter_caminho_cache_historico(matricula)
    if not caminho_cache or not os.path.exists(caminho_cache):
        return None
    with open(caminho_cache, "r", encoding="utf-8", errors="ignore") as arquivo:
        payload = json.load(arquivo)
    if isinstance(payload, dict):
        return payload
    return None


def obter_caminho_cache_formulario(matricula: str) -> str:
    matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
    if len(matricula_norm) != 9:
        return ""
    return os.path.join(localizar_diretorio_cache_formularios(), f"{matricula_norm}.json")


def salvar_cache_formulario_por_matricula(matricula: str, dados_formulario: Dict[str, Any]) -> bool:
    matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
    if len(matricula_norm) != 9 or not isinstance(dados_formulario, dict) or not dados_formulario:
        return False

    os.makedirs(localizar_diretorio_cache_formularios(), exist_ok=True)
    payload = {
        "matricula": matricula_norm,
        "salvo_em": datetime.now().isoformat(timespec="seconds"),
        "dados_formulario": dados_formulario,
    }
    caminho_cache = obter_caminho_cache_formulario(matricula_norm)
    if not caminho_cache:
        return False
    with open(caminho_cache, "w", encoding="utf-8") as arquivo:
        json.dump(payload, arquivo, ensure_ascii=False, indent=2)
    return True


def carregar_cache_formulario_por_matricula(matricula: str) -> Optional[Dict[str, Any]]:
    caminho_cache = obter_caminho_cache_formulario(matricula)
    if not caminho_cache or not os.path.exists(caminho_cache):
        return None
    with open(caminho_cache, "r", encoding="utf-8", errors="ignore") as arquivo:
        payload = json.load(arquivo)
    if isinstance(payload, dict):
        return payload
    return None


def calcular_hash_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def calcular_chave_cache_ocr_arquivos(
    caminhos_arquivo: List[str],
    recortes_por_arquivo: Dict[str, Tuple[int, int, int, int]],
    modelo: str,
) -> str:
    h = hashlib.sha256()
    h.update(b"observacoes-ano-geral-v1")
    h.update(str(modelo or "").encode("utf-8"))
    h.update(str(OCR_IA_MAX_IMAGE_SIDE).encode("ascii"))
    h.update(str(OCR_IA_JPEG_QUALITY).encode("ascii"))
    h.update(OCR_IA_REASONING_EFFORT.encode("ascii", errors="ignore"))

    for caminho in caminhos_arquivo:
        caminho_limpo = str(caminho or "").strip()
        h.update(os.path.basename(caminho_limpo).encode("utf-8", errors="ignore"))
        h.update(str(os.path.getsize(caminho_limpo)).encode("ascii"))
        h.update(calcular_hash_arquivo(caminho_limpo).encode("ascii"))
        recorte = recortes_por_arquivo.get(caminho_limpo)
        h.update(repr(tuple(recorte) if recorte else None).encode("ascii"))
    return h.hexdigest()


def obter_caminho_cache_ocr_arquivos(chave_cache: str) -> str:
    chave = re.sub(r"[^a-fA-F0-9]", "", str(chave_cache or ""))[:64]
    if len(chave) < 16:
        return ""
    return os.path.join(localizar_diretorio_cache_ocr_arquivos(), f"{chave}.json")


def carregar_cache_ocr_arquivos(chave_cache: str) -> Optional[Dict[str, Any]]:
    caminho_cache = obter_caminho_cache_ocr_arquivos(chave_cache)
    if not caminho_cache or not os.path.exists(caminho_cache):
        return None
    with open(caminho_cache, "r", encoding="utf-8", errors="ignore") as arquivo:
        payload = json.load(arquivo)
    if isinstance(payload, dict):
        return payload
    return None


def salvar_cache_ocr_arquivos(
    chave_cache: str,
    resultado_ia: Dict[str, Any],
    arquivos_scan: List[str],
    modelo: str,
) -> bool:
    if not chave_cache or not isinstance(resultado_ia, dict) or not resultado_ia:
        return False
    os.makedirs(localizar_diretorio_cache_ocr_arquivos(), exist_ok=True)
    payload = {
        "chave_cache": chave_cache,
        "salvo_em": datetime.now().isoformat(timespec="seconds"),
        "modelo": modelo,
        "arquivos_scan": list(arquivos_scan or []),
        "resultado_ia": resultado_ia,
    }
    caminho_cache = obter_caminho_cache_ocr_arquivos(chave_cache)
    if not caminho_cache:
        return False
    with open(caminho_cache, "w", encoding="utf-8") as arquivo:
        json.dump(payload, arquivo, ensure_ascii=False, indent=2)
    return True


def matricula_deve_historico(matricula: str) -> bool:
    payload = carregar_cache_formulario_por_matricula(matricula)
    if not payload:
        return False
    dados_formulario = payload.get("dados_formulario", {})
    if not isinstance(dados_formulario, dict):
        return False
    valor = dados_formulario.get("deve_historico", False)
    if isinstance(valor, bool):
        return valor
    return normalizar_sim_nao(valor) == "sim" or str(valor).strip().lower() in {"true", "1"}


def salvar_status_deve_historico_por_matricula(
    matricula: str,
    deve_historico: bool,
    nome_aluno: str = "",
) -> bool:
    matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
    if len(matricula_norm) != 9:
        return False

    payload = carregar_cache_formulario_por_matricula(matricula_norm) or {}
    dados_formulario = payload.get("dados_formulario", {})
    if not isinstance(dados_formulario, dict):
        dados_formulario = {}

    dados_formulario["numero_matricula"] = matricula_norm
    if nome_aluno and not str(dados_formulario.get("nome_aluno", "") or "").strip():
        dados_formulario["nome_aluno"] = nome_aluno
    dados_formulario["deve_historico"] = bool(deve_historico)

    return salvar_cache_formulario_por_matricula(matricula_norm, dados_formulario)


def localizar_csv_alunos() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for nome_arquivo in ("lista_alunos.csv", "liste_alunos.csv"):
        caminho = os.path.join(base_dir, nome_arquivo)
        if os.path.exists(caminho):
            return caminho
    return os.path.join(base_dir, "lista_alunos.csv")


def carregar_lista_alunos_por_nome(caminho_csv: str) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    if not os.path.exists(caminho_csv):
        raise FileNotFoundError(
            f"Arquivo de alunos nao encontrado: {caminho_csv}. "
            "Crie 'lista_alunos.csv' na mesma pasta do programa."
        )

    with open(caminho_csv, "r", encoding="utf-8-sig", errors="ignore", newline="") as arquivo:
        amostra = arquivo.read(4096)
        arquivo.seek(0)
        delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
        leitor = csv.DictReader(arquivo, delimiter=delimitador)
        campos = leitor.fieldnames or []

        campo_matricula = None
        campo_nome = None
        for campo in campos:
            campo_norm = normalizar_texto_busca(campo).replace(" ", "_")
            if campo_matricula is None and campo_norm in {"MATRICULA", "NUMERO_MATRICULA", "RA"}:
                campo_matricula = campo
            if campo_nome is None and campo_norm in {"NOME", "NOME_ALUNO", "ALUNO", "NOME_DO_ALUNO"}:
                campo_nome = campo

        if not campo_matricula:
            if not campos:
                raise ValueError("CSV sem cabecalho valido.")
            campo_matricula = campos[0]

        if not campo_nome:
            raise ValueError(
                "CSV precisa de uma coluna de nome do aluno. Exemplo de cabecalho: matricula;nome"
            )

        matriculas_por_nome: Dict[str, List[str]] = {}
        nome_original_por_norm: Dict[str, str] = {}
        for linha in leitor:
            matricula = str((linha.get(campo_matricula) or "")).strip()
            nome_original = str((linha.get(campo_nome) or "")).strip()
            nome_norm = normalizar_texto_busca(nome_original)
            if not nome_norm or not matricula:
                continue
            if nome_norm not in matriculas_por_nome:
                matriculas_por_nome[nome_norm] = []
            if matricula not in matriculas_por_nome[nome_norm]:
                matriculas_por_nome[nome_norm].append(matricula)
            nome_original_por_norm[nome_norm] = nome_original

    if not matriculas_por_nome:
        raise ValueError("Nenhum registro valido foi encontrado em lista_alunos.csv.")
    return matriculas_por_nome, nome_original_por_norm


def detectar_matriculas_duplicadas_csv(caminho_csv: str) -> Dict[str, List[str]]:
    if not os.path.exists(caminho_csv):
        raise FileNotFoundError(
            f"Arquivo de alunos nao encontrado: {caminho_csv}. "
            "Crie 'lista_alunos.csv' na mesma pasta do programa."
        )

    with open(caminho_csv, "r", encoding="utf-8-sig", errors="ignore", newline="") as arquivo:
        amostra = arquivo.read(4096)
        arquivo.seek(0)
        delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
        leitor = csv.DictReader(arquivo, delimiter=delimitador)
        campos = leitor.fieldnames or []

        campo_matricula = None
        campo_nome = None
        for campo in campos:
            campo_norm = normalizar_texto_busca(campo).replace(" ", "_")
            if campo_matricula is None and campo_norm in {"MATRICULA", "NUMERO_MATRICULA", "RA"}:
                campo_matricula = campo
            if campo_nome is None and campo_norm in {"NOME", "NOME_ALUNO", "ALUNO", "NOME_DO_ALUNO"}:
                campo_nome = campo

        if not campo_matricula:
            if not campos:
                raise ValueError("CSV sem cabecalho valido.")
            campo_matricula = campos[0]

        if not campo_nome:
            raise ValueError(
                "CSV precisa de uma coluna de nome do aluno. Exemplo de cabecalho: matricula;nome"
            )

        nomes_por_matricula: Dict[str, Dict[str, str]] = {}
        for linha in leitor:
            matricula = re.sub(r"\D", "", str((linha.get(campo_matricula) or "")).strip())
            nome_original = str((linha.get(campo_nome) or "")).strip()
            nome_norm = normalizar_texto_busca(nome_original)
            if not matricula or not nome_norm:
                continue
            if matricula not in nomes_por_matricula:
                nomes_por_matricula[matricula] = {}
            nomes_por_matricula[matricula][nome_norm] = nome_original

    duplicadas: Dict[str, List[str]] = {}
    for matricula, nomes_norm in nomes_por_matricula.items():
        nomes_unicos = sorted({nome for nome in nomes_norm.values() if nome.strip()})
        if len(nomes_unicos) > 1:
            duplicadas[matricula] = nomes_unicos
    return duplicadas


def buscar_nomes_por_matricula_csv(caminho_csv: str, matricula_alvo: str) -> Tuple[int, List[str]]:
    matricula_alvo = re.sub(r"\D", "", str(matricula_alvo or "").strip())
    if not matricula_alvo:
        return 0, []

    if not os.path.exists(caminho_csv):
        raise FileNotFoundError(
            f"Arquivo de alunos nao encontrado: {caminho_csv}. "
            "Crie 'lista_alunos.csv' na mesma pasta do programa."
        )

    with open(caminho_csv, "r", encoding="utf-8-sig", errors="ignore", newline="") as arquivo:
        amostra = arquivo.read(4096)
        arquivo.seek(0)
        delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
        leitor = csv.DictReader(arquivo, delimiter=delimitador)
        campos = leitor.fieldnames or []

        campo_matricula = None
        campo_nome = None
        for campo in campos:
            campo_norm = normalizar_texto_busca(campo).replace(" ", "_")
            if campo_matricula is None and campo_norm in {"MATRICULA", "NUMERO_MATRICULA", "RA"}:
                campo_matricula = campo
            if campo_nome is None and campo_norm in {"NOME", "NOME_ALUNO", "ALUNO", "NOME_DO_ALUNO"}:
                campo_nome = campo

        if not campo_matricula:
            if not campos:
                raise ValueError("CSV sem cabecalho valido.")
            campo_matricula = campos[0]

        if not campo_nome:
            raise ValueError(
                "CSV precisa de uma coluna de nome do aluno. Exemplo de cabecalho: matricula;nome"
            )

        nomes_encontrados: Dict[str, str] = {}
        total_ocorrencias = 0
        for linha in leitor:
            matricula = re.sub(r"\D", "", str((linha.get(campo_matricula) or "")).strip())
            if matricula != matricula_alvo:
                continue
            total_ocorrencias += 1
            nome_original = str((linha.get(campo_nome) or "")).strip()
            nome_norm = normalizar_texto_busca(nome_original)
            if not nome_norm:
                continue
            nomes_encontrados[nome_norm] = nome_original

    return total_ocorrencias, sorted(nomes_encontrados.values())


def buscar_matriculas_por_nome(
    nome_aluno: str, matriculas_por_nome: Dict[str, List[str]]
) -> Tuple[str, List[str], float]:
    nome_norm = normalizar_texto_busca(nome_aluno)
    if not nome_norm:
        return "", [], 0.0

    if nome_norm in matriculas_por_nome:
        return nome_norm, list(matriculas_por_nome[nome_norm]), 1.0

    candidatos = difflib.get_close_matches(nome_norm, list(matriculas_por_nome.keys()), n=1, cutoff=0.84)
    if not candidatos:
        return "", [], 0.0

    escolhido = candidatos[0]
    score = difflib.SequenceMatcher(None, nome_norm, escolhido).ratio()
    return escolhido, list(matriculas_por_nome.get(escolhido, [])), score


def localizar_csv_rel_aluno() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "rel_aluno.csv")


def carregar_rel_aluno_csv(caminho_csv: str) -> List[Dict[str, str]]:
    if not os.path.exists(caminho_csv):
        raise FileNotFoundError(
            f"Arquivo rel_aluno nao encontrado: {caminho_csv}. "
            "Crie 'rel_aluno.csv' na mesma pasta do programa."
        )

    with open(caminho_csv, "r", encoding="utf-8-sig", errors="ignore", newline="") as arquivo:
        amostra = arquivo.read(4096)
        arquivo.seek(0)
        delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
        leitor = csv.DictReader(arquivo, delimiter=delimitador)
        campos = leitor.fieldnames or []
        mapa_campos: Dict[str, str] = {}

        for campo in campos:
            campo_norm = normalizar_texto_busca(campo).replace(" ", "_")
            if campo_norm in {"MATRICULA", "NUMERO_MATRICULA", "RA"} and "matricula" not in mapa_campos:
                mapa_campos["matricula"] = campo
            elif campo_norm in {"NOME", "NOME_ALUNO", "NOME_DO_ALUNO", "ALUNO"} and "nome_aluno" not in mapa_campos:
                mapa_campos["nome_aluno"] = campo
            elif campo_norm == "SEXO" and "sexo" not in mapa_campos:
                mapa_campos["sexo"] = campo
            elif campo_norm in {"DATA_NASCIMENTO", "DATA_DE_NASCIMENTO", "NASCIMENTO"} and "data_nascimento" not in mapa_campos:
                mapa_campos["data_nascimento"] = campo
            elif campo_norm == "NATURALIDADE" and "naturalidade" not in mapa_campos:
                mapa_campos["naturalidade"] = campo
            elif campo_norm == "PAI" and "pai" not in mapa_campos:
                mapa_campos["pai"] = campo
            elif campo_norm == "MAE" and "mae" not in mapa_campos:
                mapa_campos["mae"] = campo

        for campo in campos:
            chave = normalizar_texto_busca(campo).replace(" ", "_")
            aliases = {
                "DATA_MATRICULA": "data_matricula", "DATA_DA_MATRICULA": "data_matricula",
                "DATA_DE_MATRICULA": "data_matricula", "DATA_AFASTAMENTO": "data_afastamento",
                "DATA_DE_AFASTAMENTO": "data_afastamento", "DATA_DO_AFASTAMENTO": "data_afastamento",
                "TURMA": "turma", "SITUACAO": "situacao", "SITUACAO_DO_ALUNO": "situacao",
                "TELEFONE_CELULAR": "telefone_celular", "TELEFONE_COMERCIAL": "telefone_comercial",
                "TELEFONE_RESIDENCIAL": "telefone_residencial",
                "TELEFONE_RESPONSAVEL": "telefone_responsavel", "TELEFONE_DO_RESPONSAVEL": "telefone_responsavel",
            }
            if chave in aliases:
                mapa_campos[aliases[chave]] = campo

        if "matricula" not in mapa_campos or "nome_aluno" not in mapa_campos:
            raise ValueError(
                "rel_aluno.csv precisa ao menos das colunas de matricula e nome do aluno."
            )

        registros: List[Dict[str, str]] = []
        for linha in leitor:
            registro = {
                "matricula": re.sub(r"\D", "", str((linha.get(mapa_campos["matricula"]) or "")).strip()),
                "nome_aluno": str((linha.get(mapa_campos["nome_aluno"]) or "")).strip(),
                "sexo": str((linha.get(mapa_campos.get("sexo", "")) or "")).strip() if mapa_campos.get("sexo") else "",
                "data_nascimento": str((linha.get(mapa_campos.get("data_nascimento", "")) or "")).strip() if mapa_campos.get("data_nascimento") else "",
                "naturalidade": str((linha.get(mapa_campos.get("naturalidade", "")) or "")).strip() if mapa_campos.get("naturalidade") else "",
                "pai": str((linha.get(mapa_campos.get("pai", "")) or "")).strip() if mapa_campos.get("pai") else "",
                "mae": str((linha.get(mapa_campos.get("mae", "")) or "")).strip() if mapa_campos.get("mae") else "",
            }
            for chave in ("data_matricula", "data_afastamento", "turma", "situacao",
                          "telefone_celular", "telefone_comercial", "telefone_residencial", "telefone_responsavel"):
                registro[chave] = str(linha.get(mapa_campos.get(chave, "")) or "").strip()
            if registro["matricula"] or registro["nome_aluno"]:
                registros.append(registro)

    if not registros:
        raise ValueError("Nenhum registro valido foi encontrado em rel_aluno.csv.")
    return registros


def normalizar_data_comparacao(valor: Any) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    numeros = re.sub(r"\D", "", texto)
    if len(numeros) == 8:
        return f"{numeros[:2]}/{numeros[2:4]}/{numeros[4:]}"
    return texto


def comparar_valor_documento(chave: str, valor_documento: Any, valor_csv: Any) -> bool:
    doc = str(valor_documento or "").strip()
    csv_val = str(valor_csv or "").strip()
    if not doc or not csv_val:
        return False
    if chave == "data_nascimento":
        return normalizar_data_comparacao(doc) == normalizar_data_comparacao(csv_val)
    if chave == "sexo":
        return normalizar_texto_busca(doc)[:1] == normalizar_texto_busca(csv_val)[:1]
    if chave == "nome_aluno":
        return difflib.SequenceMatcher(
            None,
            normalizar_texto_busca(doc),
            normalizar_texto_busca(csv_val),
        ).ratio() >= 0.92
    return normalizar_texto_busca(doc) == normalizar_texto_busca(csv_val)


def comparar_documento_com_rel_aluno(
    documento: Dict[str, Any],
    registros: List[Dict[str, str]],
    matricula_preferencial: str = "",
) -> Dict[str, Any]:
    matricula_preferencial = re.sub(r"\D", "", str(matricula_preferencial or "").strip())
    documento_nome = str(documento.get("nome_aluno", "") or "").strip()
    documento_data = normalizar_data_comparacao(documento.get("data_nascimento", ""))

    candidatos = registros
    origem = "nome"
    if matricula_preferencial:
        candidatos_matricula = [r for r in registros if r.get("matricula") == matricula_preferencial]
        if candidatos_matricula:
            candidatos = candidatos_matricula
            origem = "matricula"

    melhor_registro = None
    melhor_score = -1.0

    for registro in candidatos:
        score = 0.0
        if documento_nome and registro.get("nome_aluno"):
            score += difflib.SequenceMatcher(
                None,
                normalizar_texto_busca(documento_nome),
                normalizar_texto_busca(registro.get("nome_aluno", "")),
            ).ratio() * 0.55
        if documento_data and registro.get("data_nascimento"):
            if comparar_valor_documento("data_nascimento", documento_data, registro.get("data_nascimento", "")):
                score += 0.25
            else:
                score -= 0.12
        if comparar_valor_documento("mae", documento.get("mae", ""), registro.get("mae", "")):
            score += 0.12
        if comparar_valor_documento("pai", documento.get("pai", ""), registro.get("pai", "")):
            score += 0.08
        if comparar_valor_documento("sexo", documento.get("sexo", ""), registro.get("sexo", "")):
            score += 0.05
        if comparar_valor_documento("naturalidade", documento.get("naturalidade", ""), registro.get("naturalidade", "")):
            score += 0.05
        if origem == "matricula":
            score += 0.25

        if score > melhor_score:
            melhor_score = score
            melhor_registro = registro

    if not melhor_registro or (origem != "matricula" and melhor_score < 0.45):
        return {
            "registro": None,
            "score": melhor_score,
            "resumo": "Documento lido, mas nao encontrei um cadastro confiavel em rel_aluno.csv para comparar.",
        }

    campos = [
        ("nome_aluno", "Nome"),
        ("sexo", "Sexo"),
        ("data_nascimento", "Data Nascimento"),
        ("naturalidade", "Naturalidade"),
        ("pai", "Pai"),
        ("mae", "Mae"),
    ]
    iguais: List[str] = []
    divergentes: List[str] = []
    ausentes: List[str] = []

    for chave, rotulo in campos:
        valor_doc = str(documento.get(chave, "") or "").strip()
        valor_csv = str(melhor_registro.get(chave, "") or "").strip()
        if valor_doc and valor_csv:
            if comparar_valor_documento(chave, valor_doc, valor_csv):
                iguais.append(rotulo)
            else:
                divergentes.append(f"{rotulo} (doc: {valor_doc} / CSV: {valor_csv})")
        elif valor_doc or valor_csv:
            ausentes.append(rotulo)

    cabecalho = (
        f"Comparacao com rel_aluno.csv por {'matricula' if origem == 'matricula' else 'similaridade'}: "
        f"matricula {melhor_registro.get('matricula', '')} | "
        f"aluno {melhor_registro.get('nome_aluno', '')}."
    )
    partes = [cabecalho]
    if iguais:
        partes.append("Campos coincidentes: " + ", ".join(iguais) + ".")
    if divergentes:
        partes.append("Divergencias: " + " | ".join(divergentes) + ".")
    if ausentes:
        partes.append("Campos sem comparacao completa: " + ", ".join(ausentes) + ".")
    partes.append(f"Confianca estimada: {max(0.0, melhor_score):.0%}.")

    return {
        "registro": melhor_registro,
        "score": melhor_score,
        "resumo": " ".join(partes).strip(),
    }


def escolher_matricula_em_janela(parent: tk.Misc, nome_aluno: str, matriculas: List[str]) -> Optional[str]:
    opcoes = [str(m).strip() for m in matriculas if str(m).strip()]
    if not opcoes:
        return None
    if len(opcoes) == 1:
        return opcoes[0]

    resultado = {"valor": None}
    janela = tk.Toplevel(parent)
    janela.title("Escolher Matricula")
    janela.transient(parent)
    janela.grab_set()
    janela.resizable(False, False)
    maximizar_janela_tk(janela)

    ttk.Label(
        janela,
        text=f"Aluno: {nome_aluno}\nForam encontradas {len(opcoes)} matriculas. Selecione a correta:",
        justify="left",
    ).pack(padx=12, pady=(12, 8), anchor="w")

    lista = tk.Listbox(janela, height=min(8, len(opcoes)), exportselection=False)
    for item in opcoes:
        lista.insert(tk.END, item)
    lista.selection_set(0)
    lista.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    botoes = ttk.Frame(janela)
    botoes.pack(fill="x", padx=12, pady=(0, 12))

    def confirmar():
        selecionado = lista.curselection()
        if not selecionado:
            messagebox.showwarning("Matricula", "Selecione uma matricula.", parent=janela)
            return
        resultado["valor"] = opcoes[selecionado[0]]
        janela.destroy()

    def cancelar():
        resultado["valor"] = None
        janela.destroy()

    ttk.Button(botoes, text="OK", command=confirmar).pack(side="left")
    ttk.Button(botoes, text="Cancelar", command=cancelar).pack(side="left", padx=8)

    janela.protocol("WM_DELETE_WINDOW", cancelar)
    janela.bind("<Return>", lambda _event: confirmar())
    janela.bind("<Escape>", lambda _event: cancelar())
    parent.wait_window(janela)
    return resultado["valor"]


def escolher_nome_para_matricula_em_janela(
    parent: tk.Misc, matricula: str, nomes: List[str]
) -> Optional[str]:
    opcoes = [str(nome).strip() for nome in nomes if str(nome).strip()]
    if not opcoes:
        return None
    if len(opcoes) == 1:
        return opcoes[0]

    resultado = {"valor": None}
    janela = tk.Toplevel(parent)
    janela.title("Matricula duplicada")
    janela.transient(parent)
    janela.grab_set()
    janela.resizable(False, False)
    maximizar_janela_tk(janela)

    ttk.Label(
        janela,
        text=(
            f"Matricula: {matricula}\n"
            f"Foram encontrados {len(opcoes)} nomes no CSV. Selecione o correto:"
        ),
        justify="left",
    ).pack(padx=12, pady=(12, 8), anchor="w")

    lista = tk.Listbox(janela, height=min(8, len(opcoes)), exportselection=False)
    for item in opcoes:
        lista.insert(tk.END, item)
    lista.selection_set(0)
    lista.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    botoes = ttk.Frame(janela)
    botoes.pack(fill="x", padx=12, pady=(0, 12))

    def confirmar():
        selecionado = lista.curselection()
        if not selecionado:
            messagebox.showwarning("Matricula", "Selecione um nome.", parent=janela)
            return
        resultado["valor"] = opcoes[selecionado[0]]
        janela.destroy()

    def cancelar():
        resultado["valor"] = None
        janela.destroy()

    ttk.Button(botoes, text="OK", command=confirmar).pack(side="left")
    ttk.Button(botoes, text="Cancelar", command=cancelar).pack(side="left", padx=8)

    janela.protocol("WM_DELETE_WINDOW", cancelar)
    janela.bind("<Return>", lambda _event: confirmar())
    janela.bind("<Escape>", lambda _event: cancelar())
    parent.wait_window(janela)
    return resultado["valor"]


def normalizar_registro_historico(registro: Dict[str, Any]) -> Dict[str, str]:
    if not isinstance(registro, dict):
        return {}

    registro = dict(registro)
    extras = registro.get("disciplinas_extra", [])
    if isinstance(extras, list):
        registro["disciplinas_extra"] = [dict(item) if isinstance(item, dict) else item for item in extras]
    registro = converter_conceitos_em_observacoes(registro)

    ano = extrair_ano_4_digitos(registro.get("ano", ""))
    if not ano:
        return {}

    serie_bruta = str(registro.get("serie", "") or "").strip()
    serie_norm = normalizar_serie(serie_bruta)

    saida = {
        "ano": ano,
        "serie": serie_norm or serie_bruta,
        "nome_escola": str(registro.get("nome_escola", "") or "").strip(),
        "cidade": str(registro.get("cidade", "") or "").strip(),
        "uf": normalizar_texto_busca(str(registro.get("uf", "") or "").strip())[:2],
        "carga_horaria": str(registro.get("carga_horaria", "") or "").strip(),
        "txt_observacoes": str(registro.get("txt_observacoes", "") or "").strip(),
        "txt_observacoes_gerais": str(registro.get("txt_observacoes_gerais", "") or "").strip(),
        "cursando": normalizar_cursando_por_ano(ano, registro.get("cursando", "")),
    }

    for chave_nota in CHAVES_NOTAS:
        saida[chave_nota] = limpar_nota_extraida(registro.get(chave_nota, ""))

    aplicar_equivalencias_de_disciplinas(registro, saida)

    return saida


def mesclar_registro_historico(base: Dict[str, str], novo: Dict[str, str]) -> Dict[str, str]:
    if not base:
        return dict(novo)
    combinado = dict(base)
    for chave, valor in novo.items():
        if not combinado.get(chave) and valor:
            combinado[chave] = valor
    return combinado


def construir_historicos_por_ano(resultado_ia: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    historicos_por_ano: Dict[str, Dict[str, str]] = {}

    historicos_extraidos = resultado_ia.get("historicos", [])
    if isinstance(historicos_extraidos, list):
        for item in historicos_extraidos:
            registro = normalizar_registro_historico(item)
            if not registro:
                continue
            ano = registro["ano"]
            historicos_por_ano[ano] = mesclar_registro_historico(historicos_por_ano.get(ano, {}), registro)

    fallback = normalizar_registro_historico(resultado_ia)
    if fallback:
        ano = fallback["ano"]
        historicos_por_ano[ano] = mesclar_registro_historico(historicos_por_ano.get(ano, {}), fallback)

    observacao_geral = str(resultado_ia.get("txt_observacoes_gerais", "") or "").strip()
    for registro in historicos_por_ano.values():
        registro["txt_observacoes_gerais"] = mesclar_textos_observacao(
            observacao_geral, registro.get("txt_observacoes_gerais", "")
        )
    return dict(sorted(historicos_por_ano.items(), key=lambda item: item[0]))


def carregar_prompt_historico() -> str:
    caminhos = []
    caminho_env = (os.getenv("HISTORICO_PROMPT_PATH") or "").strip()
    if caminho_env:
        caminhos.append(caminho_env)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    caminhos.append(os.path.join(base_dir, "prompt_202603051025.txt"))

    for caminho in caminhos:
        if caminho and os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8", errors="ignore") as arquivo:
                prompt = arquivo.read().strip()
                if prompt:
                    return prompt

    return (
        "Extraia as informacoes do historico escolar em portugues do Brasil. "
        "Mantenha fidelidade ao documento original sem inventar dados. "
        "Use a tabela principal com as disciplinas padrao na ordem: "
        + ", ".join(DISCIPLINAS_TABELA)
        + ". "
        "Retorne TODOS os anos/series encontrados no campo 'historicos'. "
        "Padronize 'serie' no formato ordinal (ex.: 1º ANO, 2º ANO). "
        "Quando houver nome equivalente de disciplina (ex.: Ciencias da Natureza), "
        "mapeie para o campo principal e, se necessario, inclua em 'disciplinas_extra'. "
        "Se houver conceito em vez de nota numerica, nao preencha nota_* com a sigla; "
        "descreva isso de forma sucinta em txt_observacoes, listando as materias avaliadas por conceito. "
        "Disciplinas fora da tabela principal devem ir para txt_observacoes. "
        "Se algum campo nao estiver presente, retorne string vazia."
    )


def extrair_texto_local(caminho_arquivo: str) -> str:
    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    if extensao in {".txt", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        from historico_local_conceitos import extract_text_from_file
        return extract_text_from_file(caminho_arquivo)
    raise ValueError(f"Formato nao suportado para extracao local: {extensao}")


def extrair_texto_resposta_openai(resposta: Dict[str, Any]) -> str:
    texto_direto = resposta.get("output_text")
    if isinstance(texto_direto, str) and texto_direto.strip():
        return texto_direto.strip()

    textos = []
    for item in resposta.get("output", []):
        for conteudo in item.get("content", []):
            texto = conteudo.get("text")
            if isinstance(texto, str) and texto.strip():
                textos.append(texto.strip())
    return "\n".join(textos).strip()


def parse_json_seguro(texto: str) -> Dict[str, Any]:
    bruto = (texto or "").strip()
    if not bruto:
        raise ValueError("Resposta vazia da API OpenAI.")
    if bruto.startswith("```"):
        bruto = re.sub(r"^```(?:json)?\s*", "", bruto)
        bruto = re.sub(r"\s*```$", "", bruto)
    return json.loads(bruto)


def enviar_requisicao_openai_com_retry(
    url: str,
    payload: Dict[str, Any],
    api_key: str,
    timeout: int = 240,
    tentativas: int = 4,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    dados = json.dumps(payload).encode("utf-8")
    codigos_retry = {408, 409, 425, 429, 500, 502, 503, 504}
    contexto_ssl = ssl.create_default_context()
    try:
        contexto_ssl.minimum_version = ssl.TLSVersion.TLSv1_2
    except Exception:
        pass

    ultimo_erro = None

    # Transporte principal: requests (mais estavel em Windows para TLS/certificados).
    try:
        import requests
    except Exception:
        requests = None

    if requests is not None:
        for tentativa in range(1, tentativas + 1):
            try:
                resposta_http = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if tentativa < tentativas and resposta_http.status_code in codigos_retry:
                    ultimo_erro = RuntimeError(
                        f"Erro HTTP OpenAI {resposta_http.status_code}: {resposta_http.text}"
                    )
                    time.sleep(min(8, 2 ** (tentativa - 1)))
                    continue
                resposta_http.raise_for_status()
                return resposta_http.text
            except requests.exceptions.RequestException as exc:
                ultimo_erro = exc
                if tentativa < tentativas:
                    time.sleep(min(8, 2 ** (tentativa - 1)))
                    continue
                break

    # Fallback: urllib
    request = urllib.request.Request(
        url,
        data=dados,
        headers=headers,
        method="POST",
    )

    for tentativa in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=contexto_ssl) as resposta_http:
                return resposta_http.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detalhe = exc.read().decode("utf-8", errors="ignore")
            if tentativa < tentativas and exc.code in codigos_retry:
                time.sleep(min(8, 2 ** (tentativa - 1)))
                ultimo_erro = RuntimeError(f"Erro HTTP OpenAI {exc.code}: {detalhe}")
                continue
            raise RuntimeError(f"Erro HTTP OpenAI {exc.code}: {detalhe}") from exc
        except (
            urllib.error.URLError,
            ssl.SSLEOFError,
            ssl.SSLZeroReturnError,
            ssl.SSLError,
            socket.timeout,
            TimeoutError,
            ConnectionResetError,
        ) as exc:
            ultimo_erro = exc
            if tentativa < tentativas:
                time.sleep(min(8, 2 ** (tentativa - 1)))
                continue
            break

    detalhe_erro = f" Detalhe tecnico: {repr(ultimo_erro)}" if ultimo_erro else ""
    raise RuntimeError(
        "Falha de conexao com a OpenAI apos multiplas tentativas. "
        "Verifique internet, proxy/firewall/antivirus SSL e tente novamente."
        + detalhe_erro
    ) from ultimo_erro


OCR_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
OCR_SELECTOR_CANCELLED = object()


def selecionar_regiao_ocr_em_janela(parent: tk.Misc, caminho_arquivo: str, titulo: str) -> Any:
    extensao = os.path.splitext(str(caminho_arquivo or ""))[1].lower()
    if extensao not in OCR_IMAGE_EXTENSIONS:
        return None

    with Image.open(caminho_arquivo) as imagem_origem:
        imagem = imagem_origem.convert("RGB")

    largura_original, altura_original = imagem.size
    largura_tela = max(500, int(parent.winfo_screenwidth()) - 140)
    altura_tela = max(350, int(parent.winfo_screenheight()) - 260)
    limite_largura = min(1100, largura_tela)
    limite_altura = min(760, altura_tela)
    escala = min(limite_largura / largura_original, limite_altura / altura_original, 1.0)
    largura_exibicao = max(1, int(largura_original * escala))
    altura_exibicao = max(1, int(altura_original * escala))
    imagem_exibicao = imagem.resize((largura_exibicao, altura_exibicao), Image.LANCZOS)

    janela = tk.Toplevel(parent)
    janela.title(titulo)
    janela.transient(parent)
    janela.grab_set()
    janela.resizable(False, False)
    maximizar_janela_tk(janela)

    instrucoes = ttk.Label(
        janela,
        text=(
            "Arraste para delimitar a area que sera enviada ao OCR/LLM. "
            "Pressione Enter para confirmar o recorte ou use 'Imagem inteira'."
        ),
        wraplength=900,
        justify="left",
    )
    instrucoes.pack(fill="x", padx=10, pady=(10, 4))

    canvas = tk.Canvas(janela, width=largura_exibicao, height=altura_exibicao, bg="black", cursor="crosshair")
    canvas.pack(fill="both", expand=True, padx=10, pady=10)

    tk_image = ImageTk.PhotoImage(imagem_exibicao)
    canvas.create_image(0, 0, anchor="nw", image=tk_image)
    canvas.image = tk_image

    estado = {
        "inicio": None,
        "retangulo": None,
        "coords": None,
        "cancelado": False,
    }
    status_var = tk.StringVar(value="Selecione uma area e pressione Enter para continuar.")

    def limitar(valor: int, minimo: int, maximo: int) -> int:
        return max(minimo, min(maximo, valor))

    def atualizar_retangulo(x1: int, y1: int, x2: int, y2: int):
        if estado["retangulo"] is None:
            estado["retangulo"] = canvas.create_rectangle(x1, y1, x2, y2, outline="#ff3b30", width=2)
        else:
            canvas.coords(estado["retangulo"], x1, y1, x2, y2)

    def ao_pressionar(event):
        x = limitar(event.x, 0, largura_exibicao)
        y = limitar(event.y, 0, altura_exibicao)
        estado["inicio"] = (x, y)
        estado["coords"] = None
        atualizar_retangulo(x, y, x, y)

    def ao_arrastar(event):
        if not estado["inicio"]:
            return
        x1, y1 = estado["inicio"]
        x2 = limitar(event.x, 0, largura_exibicao)
        y2 = limitar(event.y, 0, altura_exibicao)
        atualizar_retangulo(x1, y1, x2, y2)

    def ao_soltar(event):
        if not estado["inicio"]:
            return
        x1, y1 = estado["inicio"]
        x2 = limitar(event.x, 0, largura_exibicao)
        y2 = limitar(event.y, 0, altura_exibicao)
        if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
            estado["coords"] = None
            status_var.set("Selecao muito pequena. Refaca o arraste ou use 'Imagem inteira'.")
            return
        esquerda = min(x1, x2)
        topo = min(y1, y2)
        direita = max(x1, x2)
        baixo = max(y1, y2)
        estado["coords"] = (
            int(esquerda / escala),
            int(topo / escala),
            int(direita / escala),
            int(baixo / escala),
        )
        status_var.set("Recorte definido. Pressione Enter ou clique em 'Confirmar recorte'.")

    canvas.bind("<ButtonPress-1>", ao_pressionar)
    canvas.bind("<B1-Motion>", ao_arrastar)
    canvas.bind("<ButtonRelease-1>", ao_soltar)

    resultado = {"valor": None}

    def confirmar():
        resultado["valor"] = estado["coords"]
        janela.destroy()

    def usar_imagem_inteira():
        resultado["valor"] = None
        janela.destroy()

    def cancelar():
        estado["cancelado"] = True
        resultado["valor"] = OCR_SELECTOR_CANCELLED
        janela.destroy()

    ttk.Label(janela, textvariable=status_var, justify="left").pack(fill="x", padx=10, pady=(0, 8))

    frame_botoes = ttk.Frame(janela)
    frame_botoes.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Button(frame_botoes, text="Confirmar recorte", command=confirmar).pack(side="left")
    ttk.Button(frame_botoes, text="Imagem inteira", command=usar_imagem_inteira).pack(side="left", padx=8)
    ttk.Button(frame_botoes, text="Cancelar", command=cancelar).pack(side="right")

    janela.bind("<Return>", lambda _event: confirmar())
    janela.bind("<Escape>", lambda _event: cancelar())
    canvas.bind("<Double-Button-1>", lambda _event: confirmar())
    canvas.focus_set()

    janela.protocol("WM_DELETE_WINDOW", cancelar)
    parent.wait_window(janela)
    return resultado["valor"]


def coletar_recortes_ocr(parent: tk.Misc, caminhos: List[str], titulo_prefixo: str) -> Any:
    recortes: Dict[str, Tuple[int, int, int, int]] = {}
    imagens = [str(c).strip() for c in caminhos if os.path.splitext(str(c).strip())[1].lower() in OCR_IMAGE_EXTENSIONS]
    for indice, caminho in enumerate(imagens, start=1):
        titulo = f"{titulo_prefixo} ({indice}/{len(imagens)}) - {os.path.basename(caminho)}"
        resultado = selecionar_regiao_ocr_em_janela(parent, caminho, titulo)
        if resultado is OCR_SELECTOR_CANCELLED:
            return OCR_SELECTOR_CANCELLED
        if resultado:
            recortes[caminho] = resultado
    return recortes


def preparar_caminhos_para_ocr(
    caminhos_arquivo: List[str],
    recortes_por_arquivo: Dict[str, Tuple[int, int, int, int]],
) -> Tuple[List[str], List[str]]:
    caminhos_processados: List[str] = []
    temporarios: List[str] = []

    for caminho in caminhos_arquivo:
        caminho_limpo = str(caminho or "").strip()
        extensao = os.path.splitext(caminho_limpo)[1].lower()
        recorte = recortes_por_arquivo.get(caminho_limpo)
        if extensao not in OCR_IMAGE_EXTENSIONS:
            caminhos_processados.append(caminho_limpo)
            continue

        with Image.open(caminho_limpo) as imagem_origem:
            imagem = imagem_origem.convert("RGB")
            if recorte:
                esquerda, topo, direita, baixo = recorte
                esquerda = max(0, min(esquerda, imagem.width))
                topo = max(0, min(topo, imagem.height))
                direita = max(esquerda + 1, min(direita, imagem.width))
                baixo = max(topo + 1, min(baixo, imagem.height))
                imagem = imagem.crop((esquerda, topo, direita, baixo))

            largura, altura = imagem.size
            maior_lado = max(largura, altura)
            if maior_lado > OCR_IA_MAX_IMAGE_SIDE:
                escala = OCR_IA_MAX_IMAGE_SIDE / float(maior_lado)
                novo_tamanho = (
                    max(1, int(largura * escala)),
                    max(1, int(altura * escala)),
                )
                imagem = imagem.resize(novo_tamanho, Image.LANCZOS)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as arquivo_temporario:
            caminho_temporario = arquivo_temporario.name
        imagem.save(
            caminho_temporario,
            format="JPEG",
            quality=OCR_IA_JPEG_QUALITY,
            optimize=True,
        )
        temporarios.append(caminho_temporario)
        caminhos_processados.append(caminho_temporario)

    return caminhos_processados, temporarios


def construir_conteudo_usuario_arquivos_openai(
    caminhos_arquivo: List[str],
    limite_texto: int,
    rotulo_imagem: str,
    rotulo_pdf: str,
) -> List[Dict[str, str]]:
    conteudo_usuario: List[Dict[str, str]] = []

    for indice, caminho_atual in enumerate(caminhos_arquivo, start=1):
        extensao = os.path.splitext(caminho_atual)[1].lower()
        conteudo_usuario.append(
            {
                "type": "input_text",
                "text": f"Arquivo {indice} de {len(caminhos_arquivo)}: {os.path.basename(caminho_atual)}",
            }
        )

        if extensao in OCR_IMAGE_EXTENSIONS:
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".tif": "image/tiff",
                ".tiff": "image/tiff",
            }.get(extensao, "image/png")
            with open(caminho_atual, "rb") as arquivo:
                b64 = base64.b64encode(arquivo.read()).decode("ascii")
            conteudo_usuario.append({"type": "input_image", "image_url": f"data:{mime};base64,{b64}"})
            continue

        if extensao in {".pdf", ".txt"}:
            texto_local = extrair_texto_local(caminho_atual)
            trecho = texto_local[:limite_texto]
            limite_texto = max(0, limite_texto - len(trecho))
            conteudo_usuario.append({"type": "input_text", "text": rotulo_pdf + trecho})
            continue

        raise ValueError(
            "Formato nao suportado para IA. Use: PNG, JPG, JPEG, WEBP, TIF, TIFF, PDF ou TXT."
        )

    return conteudo_usuario


def extrair_campos_historico_com_openai(caminho_arquivo: Any, model: str = "") -> Dict[str, Any]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY nao configurada. Defina a variavel de ambiente antes de usar 'Ler com IA'."
        )

    if isinstance(caminho_arquivo, (list, tuple, set)):
        caminhos_arquivo = [str(item).strip() for item in caminho_arquivo if str(item).strip()]
    else:
        caminho_unico = str(caminho_arquivo or "").strip()
        caminhos_arquivo = [caminho_unico] if caminho_unico else []

    if not caminhos_arquivo:
        raise ValueError("Nenhum arquivo foi informado para leitura por IA.")

    for caminho in caminhos_arquivo:
        if not os.path.exists(caminho):
            raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    prompt_base = carregar_prompt_historico() + (
        " Separe as observacoes por abrangencia: txt_observacoes contem somente informacoes "
        "do ano/serie correspondente, incluindo conceitos, disciplinas extras e ocorrencias daquele ano. "
        "txt_observacoes_gerais contem somente informacoes que se aplicam ao historico inteiro, "
        "sem vinculo com um ano especifico. Uma observacao intitulada geral mas que mencione "
        "um ano/serie deve ser atribuida a esse ano em txt_observacoes. "
        "Retorne a observacao geral no nivel principal e a mesma observacao em cada item de historicos. "
        "Nao duplique o mesmo texto entre os dois campos, nao invente observacoes e use string vazia "
        "quando nao houver informacao. Se a abrangencia for incerta, mantenha no ano associado "
        "pelo documento e preserve o texto para revisao."
    )
    conteudo_usuario = [
        {
            "type": "input_text",
            "text": (
                "Extraia os campos do historico e retorne APENAS JSON valido no schema solicitado. "
                "Nao use markdown. "
                "Preencha o array 'historicos' com um item por ano/serie encontrado. "
                "Use serie sempre em formato ordinal (1º ANO, 2º ANO, etc.). "
                "Mapeie disciplinas equivalentes (ex.: Ciencias da Natureza -> nota_ciencias). "
                "Se o documento trouxer conceito em vez de nota numerica, registre isso em txt_observacoes "
                "com texto curto e listando as materias; nao coloque a sigla em nota_*. "
                "Quando necessario, use 'disciplinas_extra'."
            ),
        }
    ]
    conteudo_usuario.extend(
        construir_conteudo_usuario_arquivos_openai(
            caminhos_arquivo,
            limite_texto=220000,
            rotulo_imagem="Texto OCR da imagem para extracao:\n",
            rotulo_pdf="Texto OCR/PDF para extracao:\n",
        )
    )

    payload = {
        "model": model or OCR_IA_MODEL_PADRAO,
        "reasoning": {"effort": OCR_IA_REASONING_EFFORT},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": prompt_base}]},
            {"role": "user", "content": conteudo_usuario},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "historico_escolar_extracao",
                "strict": True,
                "schema": HISTORICO_JSON_SCHEMA,
            }
        },
    }

    corpo = enviar_requisicao_openai_com_retry(
        url="https://api.openai.com/v1/responses",
        payload=payload,
        api_key=api_key,
        timeout=OCR_IA_TIMEOUT_SEGUNDOS,
        tentativas=OCR_IA_TENTATIVAS,
    )

    resposta_json = json.loads(corpo)
    texto_modelo = extrair_texto_resposta_openai(resposta_json)
    resultado = parse_json_seguro(texto_modelo)

    for chave in HISTORICO_JSON_SCHEMA["required"]:
        if chave not in resultado or resultado[chave] is None:
            resultado[chave] = [] if chave == "historicos" else ""
    return resultado


def extrair_campos_documento_civil_com_openai(caminho_arquivo: Any, model: str = "") -> Dict[str, Any]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY nao configurada. Defina a variavel de ambiente antes de usar leitura de documento civil com IA."
        )

    if isinstance(caminho_arquivo, (list, tuple, set)):
        caminhos_arquivo = [str(item).strip() for item in caminho_arquivo if str(item).strip()]
    else:
        caminho_unico = str(caminho_arquivo or "").strip()
        caminhos_arquivo = [caminho_unico] if caminho_unico else []

    if not caminhos_arquivo:
        raise ValueError("Nenhum arquivo foi informado para leitura do documento civil por IA.")

    for caminho in caminhos_arquivo:
        if not os.path.exists(caminho):
            raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    prompt_base = (
        "Voce extrai campos de documentos civis brasileiros, especialmente certidao de nascimento e RG. "
        "Retorne apenas JSON valido no schema solicitado, sem markdown e sem inventar dados. "
        "Quando um campo nao estiver legivel ou ausente, retorne string vazia."
    )
    conteudo_usuario = [
        {
            "type": "input_text",
            "text": (
                "Extraia do documento civil os campos: tipo_documento, nome_aluno, sexo, data_nascimento, "
                "naturalidade, pai, mae e numero_documento. "
                "Em RG, se pai/mae nao estiverem presentes, retorne string vazia nesses campos. "
                "Use data_nascimento no formato dd/mm/aaaa quando possivel."
            ),
        }
    ]
    conteudo_usuario.extend(
        construir_conteudo_usuario_arquivos_openai(
            caminhos_arquivo,
            limite_texto=120000,
            rotulo_imagem="Texto OCR da imagem do documento para extracao:\n",
            rotulo_pdf="Texto OCR/PDF do documento para extracao:\n",
        )
    )

    payload = {
        "model": model or OCR_IA_MODEL_PADRAO,
        "reasoning": {"effort": OCR_IA_REASONING_EFFORT},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": prompt_base}]},
            {"role": "user", "content": conteudo_usuario},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "documento_civil_extracao",
                "strict": True,
                "schema": DOCUMENTO_CIVIL_JSON_SCHEMA,
            }
        },
    }

    corpo = enviar_requisicao_openai_com_retry(
        url="https://api.openai.com/v1/responses",
        payload=payload,
        api_key=api_key,
        timeout=OCR_IA_TIMEOUT_SEGUNDOS,
        tentativas=OCR_IA_TENTATIVAS,
    )

    resposta_json = json.loads(corpo)
    texto_modelo = extrair_texto_resposta_openai(resposta_json)
    resultado = parse_json_seguro(texto_modelo)

    for chave in DOCUMENTO_CIVIL_JSON_SCHEMA["required"]:
        if chave not in resultado or resultado[chave] is None:
            resultado[chave] = ""
    return resultado

# FunÃ§Ã£o para validar o formato de data com barras
def validar_data(data_str):
    try:
        datetime.strptime(data_str, '%d/%m/%Y')  # Formato dd/mm/yyyy
        return True
    except ValueError:
        return False


def formatar_duracao(segundos: float) -> str:
    total = max(0.0, float(segundos or 0.0))
    horas, resto = divmod(int(total), 3600)
    minutos, segundos_inteiros = divmod(resto, 60)
    decimos = int((total - int(total)) * 10)
    if horas:
        return f"{horas:02}:{minutos:02}:{segundos_inteiros:02}.{decimos}"
    return f"{minutos:02}:{segundos_inteiros:02}.{decimos}"


def digita_matricula_pw(page, numero_matricula):
    matricula = str(numero_matricula).strip()
    if not matricula:
        raise ValueError('Numero de matricula vazio')
    campo = page.locator('xpath=//*[@id="txtMatricula"]')
    campo.wait_for(state='visible', timeout=15000)
    campo.click()
    campo.fill(matricula)
    preenchido = campo.input_value()
    print(f'Matricula preenchida: {preenchido}')
    campo.press('Enter')


def navegador_playwright_ativo() -> bool:
    if browser is None:
        return False
    try:
        return browser.is_connected()
    except Exception:
        return False


def pagina_playwright_ativa(subject: Any) -> bool:
    pagina = _get_base(subject)
    if pagina is None:
        return False
    try:
        return not pagina.is_closed()
    except Exception:
        return False


def _normalizar_matricula_gemul(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or "").strip())


def garantir_tela_historico_disponivel(force_reabrir: bool = False) -> bool:
    global driver, seletor, context, sessao_execucao

    if not navegador_playwright_ativo() or context is None:
        return False

    pagina = _get_base(driver)
    if pagina_playwright_ativa(pagina) and not force_reabrir:
        try:
            pagina.locator('xpath=//*[@id="txtMatricula"]').wait_for(state="visible", timeout=3000)
            driver = pagina
            seletor = SelecionarCurso(driver)
            return True
        except Exception:
            print("Tela de historico nao estava pronta. Reabrindo a pagina...")

    try:
        pagina_destino = pagina if pagina_playwright_ativa(pagina) else context.new_page()
        configurar_dialogos_automaticos(pagina_destino)
        FuncoesDoPrograma.abrir_novas_abas_pw(pagina_destino)
        driver = pagina_destino
        seletor = SelecionarCurso(driver)
        sessao_execucao["matricula_atual"] = ""
        print("Tela de historico recriada com a sessao existente.")
        return True
    except Exception as exc:
        print(f"Nao foi possivel recriar a tela de historico com a sessao atual: {exc}")
        return False


def garantir_sessao_gemul(numero_matricula: str = "", force_reabrir_tela: bool = False):
    global driver, seletor, sessao_execucao

    matricula = _normalizar_matricula_gemul(numero_matricula)
    if matricula and len(matricula) != 9:
        raise ValueError("Numero de matricula invalido. Certifique-se de que tenha 9 digitos.")

    precisa_reinicializar = (
        not sessao_execucao["navegador_inicializado"]
        or driver is None
        or not navegador_playwright_ativo()
    )

    if not precisa_reinicializar and not garantir_tela_historico_disponivel(force_reabrir=force_reabrir_tela):
        FuncoesDoPrograma.finalizar_navegador()
        precisa_reinicializar = True

    if precisa_reinicializar:
        print("Inicializando navegador e autenticando no sistema...")
        try:
            driver = FuncoesDoPrograma.abrir_chrome()
            seletor = SelecionarCurso(driver)
            FuncoesDoPrograma.logar_pw(driver)
            FuncoesDoPrograma.abrir_novas_abas_pw(driver, apos_login=True)
            sessao_execucao["navegador_inicializado"] = True
            sessao_execucao["matricula_atual"] = ""
        except Exception:
            FuncoesDoPrograma.finalizar_navegador()
            raise

    if matricula and sessao_execucao["matricula_atual"] != matricula:
        print(f"Carregando matricula {matricula} na tela de historico...")
        digita_matricula_pw(driver, matricula)
        Atalho.tab()
        time.sleep(2)
        Atalho.enter()
        sessao_execucao["matricula_atual"] = matricula

    return driver


def executar_lancamento_historico(dados: Dict[str, Any]) -> str:
    numero_matricula = re.sub(r"\D", "", str(dados.get("numero_matricula", "") or "").strip())
    if dados.get("deve_historico") or matricula_deve_historico(numero_matricula):
        raise ValueError("Aluno com historico pendente. Gere a cobranca do documento antes de continuar os lancamentos.")
    driver_ativo = garantir_sessao_gemul(numero_matricula)

    serie_bruta = str(dados.get("serie", "") or "").strip()
    serie = normalizar_serie(serie_bruta) or serie_bruta
    nome_escola = dados['nome_escola']
    cidade = dados['cidade']
    ano = exigir_ano_4_digitos(dados.get('ano'))
    uf = str(dados.get('uf', '') or UF_ESCOLA_PADRAO).strip() or UF_ESCOLA_PADRAO
    sessao_execucao["uf_atual"] = uf
    carga_horaria = dados['carga_horaria']
    ja_estudou = dados['ja_estudou']
    ficha_descritiva = dados['ficha_descritiva']
    txt_observacoes = dados['txt_observacoes']
    cursando = normalizar_cursando_por_ano(ano, dados.get('cursando', 'nao'))

    print(f"Serie: {serie}")
    print(f"Nome da Escola: {nome_escola}")
    print(f"Cidade: {cidade}")
    print(f"Ano: {ano}")
    print(f"UF: {uf}")
    print(f"Carga Horaria: {carga_horaria}")

    sessao_execucao["historico_alvo"] = dict(ano=ano, serie=serie, escola=nome_escola)
    registrar_etapa_historico("inicio_lancamento", _get_base(driver_ativo),
                             matricula=numero_matricula, **sessao_execucao["historico_alvo"])
    inicio_lancamento = time.time()
    pagina = _get_base(driver_ativo)
    pagina.goto(f"{GEMUL_HISTORICO_URL}?txtMatricula={numero_matricula}", wait_until="domcontentloaded")
    pagina.locator('#txtMatricula').wait_for(state="visible", timeout=15000)
    if pagina.locator('#txtMatricula').input_value().strip() != numero_matricula:
        raise RuntimeError('A matrícula exibida no GEMUL não corresponde à matrícula informada. Lançamento bloqueado.')
    pagina.locator('#btnIncluir').wait_for(state="attached", timeout=15000)
    linhas = pagina.locator('tr').filter(has=pagina.locator('button[onclick*="editarDisciplinas"]'))
    registros = linhas.evaluate_all("rows => rows.map(row => Array.from(row.cells).map(cell => cell.innerText.trim()))")
    indice = indice_registro_historico(registros, ano, serie, nome_escola)
    if indice is not None:
        registrar_etapa_historico("duplicacao_bloqueada", pagina, ano=ano, serie=serie, escola=nome_escola)
        return f"Registro já existente: {ano}, {serie}, {nome_escola}. Nenhum dado foi incluído."
    if serie == "AGRUPAMENTO 4":
        SerieEscolhida.agrupamento4(driver_ativo, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, cursando, dados.get("txt_observacoes_gerais", ""))
    elif serie == "AGRUPAMENTO 5":
        SerieEscolhida.agrupamento5(driver_ativo, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, cursando, dados.get("txt_observacoes_gerais", ""))
    elif serie == f"1{ORDINAL_INDICATOR} ANO":
        SerieEscolhida.ano1(driver_ativo, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados)
    elif serie == f"2{ORDINAL_INDICATOR} ANO":
        SerieEscolhida.ano2(driver_ativo, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados)
    elif serie == f"3{ORDINAL_INDICATOR} ANO":
        SerieEscolhida.ano3(driver_ativo, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados)
    elif serie == f"4{ORDINAL_INDICATOR} ANO":
        SerieEscolhida.ano4(driver_ativo, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados)
    elif serie == f"5{ORDINAL_INDICATOR} ANO":
        SerieEscolhida.ano5(driver_ativo, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados)
    else:
        raise ValueError(f"Serie nao suportada para lancamento: {serie_bruta}")

    duracao = formatar_duracao(time.time() - inicio_lancamento)
    mensagem = f"Lancamento concluido para {serie} em {duracao}."
    registrar_etapa_historico("concluido", pagina, ano=ano, serie=serie, duracao=duracao)
    print(mensagem)
    Atalho.alerta_sonoro()
    return mensagem


# Tkinter capturador de dados
def obter_matricula():
    root = tk.Tk()
    root.title("Entrada de Dados")
    maximizar_janela_tk(root)

    root.minsize(1100, 720)
    root.withdraw()

    dados = {}
    calendario_escolar = CalendarioEscolar()

    series = ["AGRUPAMENTO 4", "AGRUPAMENTO 5"] + [f"{i}{ORDINAL_INDICATOR} ANO" for i in range(1, 6)]
    historicos_por_ano: Dict[str, Dict[str, str]] = {}
    cache_csv: Dict[str, Any] = {"matriculas": None, "nomes": None}
    cache_rel_aluno: Dict[str, Any] = {"registros": None}
    bloqueio_auto = {"ativo": False}
    arquivos_scan_paths: List[str] = []
    arquivos_documento_paths: List[str] = []
    recortes_historico_por_arquivo: Dict[str, Tuple[int, int, int, int]] = {}
    recortes_documento_por_arquivo: Dict[str, Tuple[int, int, int, int]] = {}

    numero_matricula_var = tk.StringVar()
    ano_var = tk.StringVar()
    nome_escola_var = tk.StringVar(value=ESCOLA_PADRAO)
    cidade_var = tk.StringVar(value=CIDADE_ESCOLA_PADRAO)
    uf_var = tk.StringVar(value=UF_ESCOLA_PADRAO)
    serie_var = tk.StringVar()
    carga_horaria_var = tk.StringVar()
    data_matricula_var = tk.StringVar()
    data_transferencia_var = tk.StringVar()
    ja_estudou_var = tk.BooleanVar()
    ficha_descritiva_var = tk.BooleanVar()
    cursando_var = tk.BooleanVar()
    observacoes_var = tk.BooleanVar()
    deve_historico_var = tk.BooleanVar()
    gerar_cobranca_var = tk.BooleanVar()
    txt_observacoes_var = tk.StringVar()
    marcar_disciplinas_var = tk.BooleanVar()
    nome_aluno_var = tk.StringVar()
    arquivo_scan_var = tk.StringVar()
    arquivo_documento_var = tk.StringVar()
    status_scan_var = tk.StringVar(value="Nenhum arquivo processado pela IA.")
    status_documento_var = tk.StringVar(value="Nenhum documento civil processado.")
    ocr_timer_var = tk.StringVar(value="OCR parado: 00:00.0")

    disciplinas_vars = {
        "ARTES": tk.StringVar(),
        "CIÊNCIAS": tk.StringVar(),
        "CULTURA DE INOVAÇÃO E TECNOLOGIAS": tk.StringVar(),
        "EDUCAÇÃO FÍSICA": tk.StringVar(),
        "ENSINO RELIGIOSO": tk.StringVar(),
        "GEOGRAFIA": tk.StringVar(),
        "HISTÓRIA": tk.StringVar(),
        "LÍNGUA PORTUGUESA": tk.StringVar(),
        "MATEMÁTICA": tk.StringVar(),
    }

    mapa_notas_local = {
        "ARTES": "nota_arte",
        "CIÊNCIAS": "nota_ciencias",
        "CULTURA DE INOVAÇÃO E TECNOLOGIAS": "nota_cultura",
        "EDUCAÇÃO FÍSICA": "nota_educacao_fisica",
        "ENSINO RELIGIOSO": "nota_ensino_religioso",
        "GEOGRAFIA": "nota_geografia",
        "HISTÓRIA": "nota_historia",
        "LÍNGUA PORTUGUESA": "nota_lingua_portuguesa",
        "MATEMÁTICA": "nota_matematica",
    }

    disciplina_widgets: List[Tuple[tk.Widget, tk.Widget]] = []
    txt_observacoes_widget = None
    txt_observacoes_gerais_widget = None
    botao_ler_ia = None
    botao_ler_documento = None
    botao_ok = None
    progresso_ocr = None
    ocr_estado = {"ativo": False, "inicio": 0.0, "frame": 0, "job": None}
    lancamento_em_andamento = {"ativo": False}
    consulta_matricula_estado = {"ultima_consultada": "", "ultimo_alerta_deve_historico": ""}
    monitoramento_navegador = {"ativo": True, "encerrando": False}

    def obter_var_disciplina(nome_disciplina: str):
        if nome_disciplina in disciplinas_vars:
            return disciplinas_vars[nome_disciplina]
        alvo = normalizar_texto_busca(nome_disciplina)
        for chave, var in disciplinas_vars.items():
            if normalizar_texto_busca(chave) == alvo:
                return var
        return None

    def obter_texto_observacoes() -> str:
        if txt_observacoes_widget is None:
            return corrigir_texto_utf8(txt_observacoes_var.get()).strip()
        return corrigir_texto_utf8(txt_observacoes_widget.get("1.0", "end-1c")).strip()

    def definir_texto_observacoes(texto: Any):
        valor = corrigir_texto_utf8(texto)
        txt_observacoes_var.set(valor)
        if txt_observacoes_widget is not None:
            txt_observacoes_widget.delete("1.0", tk.END)
            if valor:
                txt_observacoes_widget.insert("1.0", valor)

    def obter_texto_observacoes_gerais() -> str:
        if txt_observacoes_gerais_widget is None:
            return ""
        return corrigir_texto_utf8(txt_observacoes_gerais_widget.get("1.0", "end-1c")).strip()

    def definir_texto_observacoes_gerais(texto: Any):
        if txt_observacoes_gerais_widget is not None:
            txt_observacoes_gerais_widget.delete("1.0", tk.END)
            txt_observacoes_gerais_widget.insert("1.0", corrigir_texto_utf8(texto or ""))

    def serie_fundamental_1a5(serie_texto: str) -> bool:
        serie_normalizada = normalizar_serie(serie_texto)
        return bool(serie_normalizada and serie_normalizada not in {"AGRUPAMENTO 4", "AGRUPAMENTO 5"})

    def calcular_carga_horaria():
        cidade_norm = normalizar_texto_busca(cidade_var.get())
        serie_norm = normalizar_texto_busca(serie_var.get())
        ano = extrair_ano_4_digitos(ano_var.get())

        if cidade_norm == "APARECIDA DE GOIANIA":
            if ano == "2026":
                horas_por_dia = (4 if serie_norm in {"AGRUPAMENTO 4", "AGRUPAMENTO 5"}
                                 else 5 if serie_fundamental_1a5(serie_norm) else 0)
                total_dias = calendario_escolar.calcular_dias_letivos('31/12/2026')
                return str(total_dias * horas_por_dia) if horas_por_dia else ""
            if serie_norm in {"AGRUPAMENTO 4", "AGRUPAMENTO 5"}:
                return "759" if ano == "2020" else "800"
            if serie_fundamental_1a5(serie_norm):
                return "950" if ano == "2020" else "1000"
        elif cidade_norm == "GOIANIA":
            return "800"
        return ""

    def aplicar_dados_escola_padrao():
        escola_norm = normalizar_texto_busca(nome_escola_var.get())
        if escola_norm != normalizar_texto_busca(ESCOLA_PADRAO):
            return

        if cidade_var.get().strip() != CIDADE_ESCOLA_PADRAO:
            cidade_var.set(CIDADE_ESCOLA_PADRAO)
        if uf_var.get().strip() != UF_ESCOLA_PADRAO:
            uf_var.set(UF_ESCOLA_PADRAO)

    def on_escola_change(*_args):
        if bloqueio_auto["ativo"]:
            return
        aplicar_dados_escola_padrao()
        on_transfer_date_change()

    def on_cidade_change(*_args):
        if bloqueio_auto["ativo"]:
            return
        on_transfer_date_change()

    def coletar_dados_formulario() -> Dict[str, Any]:
        dados_formulario: Dict[str, Any] = {}
        dados_formulario["numero_matricula"] = numero_matricula_var.get()
        dados_formulario["nome_aluno"] = nome_aluno_var.get()
        dados_formulario["arquivo_scan"] = arquivo_scan_var.get()
        dados_formulario["arquivos_scan"] = obter_caminhos_scan()
        dados_formulario["arquivo_documento"] = arquivo_documento_var.get()
        dados_formulario["arquivos_documento"] = obter_caminhos_documento()
        dados_formulario["ano"] = extrair_ano_4_digitos(ano_var.get())
        dados_formulario["nome_escola"] = nome_escola_var.get()
        dados_formulario["cidade"] = cidade_var.get()
        dados_formulario["uf"] = uf_var.get()
        dados_formulario["serie"] = normalizar_serie(serie_var.get()) or serie_var.get().strip()
        dados_formulario["cursando"] = normalizar_cursando_por_ano(
            dados_formulario["ano"],
            "sim" if cursando_var.get() else "nao",
        )
        dados_formulario["data_matricula"] = data_matricula_var.get()
        dados_formulario["carga_horaria"] = carga_horaria_var.get()
        dados_formulario["data_transferencia"] = data_transferencia_var.get()
        dados_formulario["ja_estudou"] = "sim" if ja_estudou_var.get() else "nao"
        dados_formulario["ficha_descritiva"] = "sim" if ficha_descritiva_var.get() else "nao"
        dados_formulario["deve_historico"] = bool(deve_historico_var.get())
        dados_formulario["observacoes"] = observacoes_var.get()
        dados_formulario["marcar_disciplinas"] = marcar_disciplinas_var.get()

        texto_obs = obter_texto_observacoes()
        dados_formulario["txt_observacoes"] = texto_obs
        dados_formulario["txt_observacoes_gerais"] = obter_texto_observacoes_gerais()
        txt_observacoes_var.set(texto_obs)

        for disciplina, var in disciplinas_vars.items():
            dados_formulario[disciplina] = var.get()

        for chave_nota in CHAVES_NOTAS:
            dados_formulario[chave_nota] = ""
        for disciplina, chave_nota in mapa_notas_local.items():
            var = obter_var_disciplina(disciplina)
            dados_formulario[chave_nota] = var.get() if var else ""

        dados.clear()
        dados.update(dados_formulario)
        return dados_formulario

    def atualizar_indicador_ocr():
        if not ocr_estado["ativo"]:
            return
        frames = ["Processando OCR   ", "Processando OCR.  ", "Processando OCR.. ", "Processando OCR..."]
        decorrido = time.time() - ocr_estado["inicio"]
        frame = frames[ocr_estado["frame"] % len(frames)]
        ocr_estado["frame"] += 1
        ocr_timer_var.set(f"{frame} {formatar_duracao(decorrido)}")
        ocr_estado["job"] = root.after(200, atualizar_indicador_ocr)

    def finalizar_indicador_ocr(texto_final: str):
        if ocr_estado["job"] is not None:
            try:
                root.after_cancel(ocr_estado["job"])
            except Exception:
                pass
        duracao = time.time() - ocr_estado["inicio"] if ocr_estado["inicio"] else 0.0
        ocr_estado["ativo"] = False
        ocr_estado["inicio"] = 0.0
        ocr_estado["job"] = None
        if progresso_ocr is not None:
            progresso_ocr.stop()
        if botao_ler_ia is not None:
            botao_ler_ia.state(["!disabled"])
        if botao_ler_documento is not None:
            botao_ler_documento.state(["!disabled"])
        ocr_timer_var.set(f"{texto_final}: {formatar_duracao(duracao)}")

    def submit():
        if lancamento_em_andamento["ativo"]:
            return

        dados_formulario = coletar_dados_formulario()
        numero_matricula = re.sub(r"\D", "", str(dados_formulario.get("numero_matricula", "") or ""))
        if len(numero_matricula) != 9:
            messagebox.showwarning(
                "Matricula",
                "Informe uma matricula valida com 9 digitos antes de lancar.",
                parent=root,
            )
            return
        if deve_historico_var.get() or matricula_deve_historico(numero_matricula):
            messagebox.showinfo(
                "Histórico pendente",
                "Este aluno deve histórico escolar. Os lançamentos estão bloqueados até a regularização. "
                "Use a opção Gerar cobrança de histórico para preparar a solicitação.", parent=root,
            )
            return
        if not str(dados_formulario.get("serie", "") or "").strip():
            messagebox.showwarning("Serie", "Informe a serie antes de lancar.", parent=root)
            return
        if not str(dados_formulario.get("ano", "") or "").strip():
            messagebox.showwarning(
                "Ano",
                "Informe o ano do historico com 4 digitos antes de lancar.",
                parent=root,
            )
            return

        lancamento_em_andamento["ativo"] = True
        if botao_ok is not None:
            botao_ok.state(["disabled"])
        status_scan_var.set(f"Lancando {dados_formulario['serie']}...")
        print(
            f"Iniciando lancamento manual: matricula={dados_formulario['numero_matricula']} "
            f"serie={dados_formulario['serie']} ano={dados_formulario['ano']}"
        )
        root.update_idletasks()
        try:
            root.configure(cursor="watch")
        except Exception:
            pass

        try:
            salvar_cache_formulario_por_matricula(numero_matricula, dados_formulario)
        except Exception as exc:
            print(f"Falha ao persistir formulario da matricula {numero_matricula}: {exc}")

        try:
            mensagem = executar_lancamento_historico(dados_formulario)
        except Exception as exc:
            traceback.print_exc()
            registrar_etapa_historico("falha", _get_base(driver), erro=str(exc), alvo=sessao_execucao.get("historico_alvo"))
            erro_texto = str(exc)
            status_scan_var.set(f"Falha no lancamento: {erro_texto}. Sessao mantida para nova tentativa.")
            messagebox.showerror(
                "Falha no lancamento",
                f"{erro_texto}\n\nA sessao do navegador foi mantida. "
                "Use \"RECUPERAR GEMUL\" ou tente novamente.",
                parent=root,
            )
        else:
            status_scan_var.set(mensagem)
            if mensagem.startswith('Registro já existente:'):
                messagebox.showinfo('Lançamento já cadastrado', mensagem, parent=root)
        finally:
            lancamento_em_andamento["ativo"] = False
            if botao_ok is not None:
                botao_ok.state(["!disabled"])
            try:
                root.configure(cursor="")
            except Exception:
                pass

    def on_transfer_date_change(*_args):
        if bloqueio_auto["ativo"]:
            return
        data_transferencia = data_transferencia_var.get().strip()
        if data_transferencia and validar_data(data_transferencia):
            try:
                total_dias = calendario_escolar.calcular_dias_letivos(data_transferencia)
            except ValueError as exc:
                carga_horaria_var.set('')
                status_scan_var.set(str(exc))
                return
            serie_norm = normalizar_texto_busca(serie_var.get())
            horas_por_dia = 4 if serie_norm in {"AGRUPAMENTO 4", "AGRUPAMENTO 5"} else 5 if serie_fundamental_1a5(serie_norm) else 0
            carga_horaria_var.set(str(total_dias * horas_por_dia) if horas_por_dia else "")
            return
        carga_horaria_var.set(calcular_carga_horaria())

    def on_serie_change(*_args):
        if bloqueio_auto["ativo"]:
            return
        on_transfer_date_change()

    def on_ano_change(*_args):
        if bloqueio_auto["ativo"]:
            return
        if aplicar_historico_por_ano(ano_var.get()):
            return
        on_transfer_date_change()

    def autocomplete(_event):
        typed = serie_var.get().strip()
        if not typed:
            serie_combobox["values"] = series
            return
        filtered = [serie for serie in series if serie.lower().startswith(typed.lower())]
        serie_combobox["values"] = filtered or series
        if len(filtered) == 1:
            serie_combobox.set(filtered[0])

    def mostrar_disciplinas():
        if not disciplina_widgets:
            return
        visivel = marcar_disciplinas_var.get()
        for label_widget, entry_widget in disciplina_widgets:
            if visivel:
                label_widget.grid()
                entry_widget.grid()
            else:
                label_widget.grid_remove()
                entry_widget.grid_remove()

    def avisar_devedor_historico(matricula: str, *, exibir_alertas: bool, atualizar_status: bool) -> bool:
        matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
        if len(matricula_norm) != 9:
            return False
        try:
            deve = matricula_deve_historico(matricula_norm)
        except Exception as exc:
            if atualizar_status:
                status_scan_var.set(f"Falha ao consultar devedor de historico: {exc}")
            return False
        if not deve:
            return False

        deve_historico_var.set(True)
        mensagem = f"Matricula {matricula_norm} marcada como DEVEDOR DE HISTORICO."
        if atualizar_status:
            status_scan_var.set(mensagem)
        if exibir_alertas and consulta_matricula_estado.get("ultimo_alerta_deve_historico") != matricula_norm:
            consulta_matricula_estado["ultimo_alerta_deve_historico"] = matricula_norm
            messagebox.showwarning("Deve historico", mensagem, parent=root)
        return True

    def salvar_deve_historico_atual():
        matricula = re.sub(r"\D", "", str(numero_matricula_var.get() or "").strip())
        if len(matricula) != 9:
            deve_historico_var.set(False)
            messagebox.showwarning(
                "Deve historico",
                "Informe uma matricula valida com 9 digitos antes de marcar.",
                parent=root,
            )
            return

        deve = bool(deve_historico_var.get())
        try:
            salvar_status_deve_historico_por_matricula(
                matricula,
                deve,
                nome_aluno_var.get().strip(),
            )
        except Exception as exc:
            traceback.print_exc()
            status_scan_var.set(f"Falha ao salvar status deve historico: {exc}")
            messagebox.showerror("Deve historico", f"Nao foi possivel salvar:\n{exc}", parent=root)
            return

        if deve:
            consulta_matricula_estado["ultimo_alerta_deve_historico"] = matricula
            status_scan_var.set(f"Matricula {matricula} registrada como devedor de historico.")
        else:
            consulta_matricula_estado["ultimo_alerta_deve_historico"] = ""
            status_scan_var.set(f"Matricula {matricula} desmarcada como devedor de historico.")

    def abrir_cobranca_historico():
        if not gerar_cobranca_var.get():
            return
        try:
            texto = gerar_texto_cobranca_historico(coletar_dados_formulario())
        except ValueError as exc:
            gerar_cobranca_var.set(False)
            messagebox.showwarning('Cobrança de histórico', str(exc), parent=root)
            return
        janela = tk.Toplevel(root)
        janela.title('Cobrança de histórico — revisar e copiar')
        janela.geometry('760x460')
        campo = tk.Text(janela, wrap='word', padx=12, pady=12)
        campo.pack(fill='both', expand=True)
        campo.insert('1.0', texto)
        botoes = ttk.Frame(janela)
        botoes.pack(fill='x', padx=10, pady=10)

        def copiar():
            try:
                root.clipboard_clear()
                root.clipboard_append(campo.get('1.0', 'end-1c'))
            except tk.TclError:
                aviso_copia.set('Não foi possível copiar. Selecione o texto e pressione Ctrl+C.')
            else:
                aviso_copia.set('Texto copiado automaticamente. Use Ctrl+V para colar.')
            status_scan_var.set(aviso_copia.get())

        aviso_copia = tk.StringVar()
        ttk.Label(janela, textvariable=aviso_copia).pack(fill='x', padx=15, pady=5)
        copiar()

        def salvar():
            destino = filedialog.asksaveasfilename(
                parent=janela, title='Salvar cobrança', defaultextension='.txt',
                initialfile=f'cobranca_historico_{numero_matricula_var.get()}.txt',
                filetypes=[('Texto', '*.txt')],
            )
            if destino:
                try:
                    with open(destino, 'w', encoding='utf-8') as arquivo:
                        arquivo.write(campo.get('1.0', 'end-1c'))
                except OSError as exc:
                    messagebox.showerror('Cobrança', f'Não foi possível salvar: {exc}', parent=janela)

        ttk.Button(botoes, text='Copiar texto', command=copiar).pack(side='left', padx=5)
        ttk.Button(botoes, text='Salvar texto...', command=salvar).pack(side='left', padx=5)
        ttk.Button(botoes, text='Fechar', command=janela.destroy).pack(side='right', padx=5)
        janela.protocol('WM_DELETE_WINDOW', janela.destroy)
        def ao_fechar(event):
            if event.widget == janela:
                gerar_cobranca_var.set(False)
        janela.bind('<Destroy>', ao_fechar)
        registrar_etapa_historico('cobranca_gerada', matricula=numero_matricula_var.get())

    def on_observacoes_text_change(_event=None):
        texto = obter_texto_observacoes()
        txt_observacoes_var.set(texto)
        if texto:
            observacoes_var.set(True)

    def atualizar_campo_arquivos(caminhos: List[str]):
        caminhos_limpos = []
        for caminho in caminhos:
            valor = str(caminho or "").strip()
            if valor and valor not in caminhos_limpos:
                caminhos_limpos.append(valor)
        arquivos_scan_paths[:] = caminhos_limpos
        arquivo_scan_var.set(" | ".join(caminhos_limpos))

    def atualizar_campo_documentos(caminhos: List[str]):
        caminhos_limpos = []
        for caminho in caminhos:
            valor = str(caminho or "").strip()
            if valor and valor not in caminhos_limpos:
                caminhos_limpos.append(valor)
        arquivos_documento_paths[:] = caminhos_limpos
        arquivo_documento_var.set(" | ".join(caminhos_limpos))

    def obter_caminhos_scan() -> List[str]:
        if arquivos_scan_paths:
            return list(arquivos_scan_paths)
        texto = arquivo_scan_var.get().strip()
        if not texto:
            return []
        partes = [parte.strip() for parte in re.split(r"\s*\|\s*|\s*;\s*", texto) if parte.strip()]
        return partes

    def recuperar_gemul():
        if lancamento_em_andamento["ativo"]:
            return

        matricula = _normalizar_matricula_gemul(numero_matricula_var.get())
        status_scan_var.set("Recuperando tela do GEMUL...")
        root.update_idletasks()

        try:
            garantir_sessao_gemul(matricula, force_reabrir_tela=True)
        except Exception as exc:
            traceback.print_exc()
            erro_texto = str(exc)
            status_scan_var.set(f"Falha ao recuperar GEMUL: {erro_texto}")
            messagebox.showerror("Falha ao recuperar GEMUL", erro_texto, parent=root)
            return

        if matricula:
            status_scan_var.set(f"Tela do GEMUL pronta para a matricula {matricula}.")
        else:
            status_scan_var.set("Tela do GEMUL pronta para novo lancamento.")

    def descobrir_arquivos_historico_automaticamente() -> List[str]:
        if not os.path.isdir(AUTO_HISTORICO_DIR):
            return []

        grupos: Dict[str, List[str]] = {}
        for nome in os.listdir(AUTO_HISTORICO_DIR):
            caminho = os.path.join(AUTO_HISTORICO_DIR, nome)
            if not os.path.isfile(caminho):
                continue
            extensao = os.path.splitext(nome)[1].lower()
            if extensao not in LLM_SUPPORTED_EXTENSIONS:
                continue
            base = os.path.splitext(nome)[0]
            grupo = re.sub(r"[_-]\d+$", "", base) or base
            grupos.setdefault(grupo, []).append(caminho)

        if not grupos:
            return []

        def chave_grupo(item: Tuple[str, List[str]]) -> float:
            _grupo, caminhos = item
            return max(os.path.getmtime(caminho) for caminho in caminhos)

        _, caminhos_escolhidos = max(grupos.items(), key=chave_grupo)

        def chave_arquivo(caminho: str) -> Tuple[int, str]:
            base = os.path.splitext(os.path.basename(caminho))[0]
            match = re.search(r"(\d+)$", base)
            indice = int(match.group(1)) if match else 0
            return indice, caminho.lower()

        return sorted(caminhos_escolhidos, key=chave_arquivo)

    def carregar_arquivos_historico_automaticamente(solicitar_recorte: bool = False) -> List[str]:
        caminhos = descobrir_arquivos_historico_automaticamente()
        if not caminhos:
            atualizar_campo_arquivos([])
            status_scan_var.set(
                f"Nenhum arquivo suportado encontrado em {AUTO_HISTORICO_DIR}."
            )
            return []

        atualizar_campo_arquivos(caminhos)
        status_scan_var.set(
            f"Lote automatico carregado de {AUTO_HISTORICO_DIR}: {len(caminhos)} arquivo(s)."
        )

        if not solicitar_recorte:
            return caminhos

        recortes = coletar_recortes_ocr(root, list(caminhos), "Selecionar area OCR do historico")
        if recortes is OCR_SELECTOR_CANCELLED:
            return []
        recortes_historico_por_arquivo.clear()
        recortes_historico_por_arquivo.update(recortes)
        if recortes_historico_por_arquivo:
            status_scan_var.set(
                f"Lote automatico carregado com {len(recortes_historico_por_arquivo)} recorte(s) OCR."
            )
        return caminhos

    def obter_caminhos_documento() -> List[str]:
        if arquivos_documento_paths:
            return list(arquivos_documento_paths)
        texto = arquivo_documento_var.get().strip()
        if not texto:
            return []
        return [parte.strip() for parte in re.split(r"\s*\|\s*|\s*;\s*", texto) if parte.strip()]

    def selecionar_arquivo_scan():
        diretorio_inicial = AUTO_HISTORICO_DIR if os.path.isdir(AUTO_HISTORICO_DIR) else os.path.dirname(os.path.abspath(__file__))
        caminhos = filedialog.askopenfilenames(
            parent=root,
            title="Selecione um ou mais arquivos do historico",
            initialdir=diretorio_inicial,
            filetypes=[
                ("Arquivos suportados", "*.png *.jpg *.jpeg *.webp *.tif *.tiff *.pdf *.txt"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not caminhos:
            return

        recortes = coletar_recortes_ocr(root, list(caminhos), "Selecionar area OCR do historico")
        if recortes is OCR_SELECTOR_CANCELLED:
            return
        recortes_historico_por_arquivo.clear()
        recortes_historico_por_arquivo.update(recortes)
        atualizar_campo_arquivos(list(caminhos))
        if recortes_historico_por_arquivo:
            status_scan_var.set(
                f"Historico selecionado manualmente com {len(recortes_historico_por_arquivo)} recorte(s) OCR."
            )
        else:
            status_scan_var.set(
                f"Historico selecionado manualmente: {len(caminhos)} arquivo(s)."
            )

    def selecionar_arquivo_documento():
        diretorio_inicial = AUTO_HISTORICO_DIR if os.path.isdir(AUTO_HISTORICO_DIR) else os.path.dirname(os.path.abspath(__file__))
        caminhos = filedialog.askopenfilenames(
            parent=root,
            title="Selecione imagem(ns) de certidao de nascimento ou RG",
            initialdir=diretorio_inicial,
            filetypes=[
                ("Arquivos suportados", "*.png *.jpg *.jpeg *.webp *.tif *.tiff *.pdf *.txt"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if caminhos:
            recortes = coletar_recortes_ocr(root, list(caminhos), "Selecionar area OCR do documento")
            if recortes is OCR_SELECTOR_CANCELLED:
                return
            recortes_documento_por_arquivo.clear()
            recortes_documento_por_arquivo.update(recortes)
            atualizar_campo_documentos(list(caminhos))
            if recortes_documento_por_arquivo:
                status_documento_var.set(
                    f"Documento selecionado com {len(recortes_documento_por_arquivo)} recorte(s) OCR."
                )

    def resetar_formulario():
        if lancamento_em_andamento["ativo"]:
            return

        bloqueio_auto["ativo"] = True
        try:
            numero_matricula_var.set("")
            nome_aluno_var.set("")
            ano_var.set("")
            nome_escola_var.set(ESCOLA_PADRAO)
            cidade_var.set(CIDADE_ESCOLA_PADRAO)
            uf_var.set(UF_ESCOLA_PADRAO)
            serie_var.set("")
            carga_horaria_var.set("")
            data_matricula_var.set("")
            data_transferencia_var.set("")
            ja_estudou_var.set(False)
            ficha_descritiva_var.set(False)
            cursando_var.set(False)
            observacoes_var.set(False)
            deve_historico_var.set(False)
            gerar_cobranca_var.set(False)
            marcar_disciplinas_var.set(False)
            definir_texto_observacoes("")
            definir_texto_observacoes_gerais("")
            for var in disciplinas_vars.values():
                var.set("")
            historicos_por_ano.clear()
            recortes_historico_por_arquivo.clear()
            recortes_documento_por_arquivo.clear()
            atualizar_campo_arquivos([])
            atualizar_campo_documentos([])
            consulta_matricula_estado["ultima_consultada"] = ""
            consulta_matricula_estado["ultimo_alerta_deve_historico"] = ""
            status_scan_var.set("Nenhum arquivo processado pela IA.")
            status_documento_var.set("Nenhum documento civil processado.")
            ocr_timer_var.set("OCR parado: 00:00.0")
            try:
                ano_combobox["values"] = []
            except Exception:
                pass
        finally:
            bloqueio_auto["ativo"] = False

        aplicar_dados_escola_padrao()
        on_transfer_date_change()
        mostrar_disciplinas()
        carregar_arquivos_historico_automaticamente(solicitar_recorte=False)
        try:
            entrada_matricula.focus_set()
        except Exception:
            pass

    def carregar_base_alunos():
        if cache_csv["matriculas"] is not None and cache_csv["nomes"] is not None:
            return cache_csv["matriculas"], cache_csv["nomes"]
        caminho_csv = localizar_csv_alunos()
        matriculas_por_nome, nomes_originais = carregar_lista_alunos_por_nome(caminho_csv)
        cache_csv["matriculas"] = matriculas_por_nome
        cache_csv["nomes"] = nomes_originais
        return matriculas_por_nome, nomes_originais

    def carregar_base_rel_aluno():
        if cache_rel_aluno["registros"] is not None:
            return cache_rel_aluno["registros"]
        caminho_csv = localizar_csv_rel_aluno()
        registros = carregar_rel_aluno_csv(caminho_csv)
        cache_rel_aluno["registros"] = registros
        return registros

    def aplicar_cadastro_matricula(matricula):
        registros = [r for r in carregar_base_rel_aluno()
                     if r["matricula"] == matricula
                     and normalizar_texto_busca(r["nome_aluno"]) == normalizar_texto_busca(nome_aluno_var.get())]
        # Avoid choosing a class or enrollment period arbitrarily.
        if len(registros) != 1:
            return False
        registro = registros[0]
        entrada = registro.get("data_matricula", "")
        saida = registro.get("data_afastamento", "")
        entrada = entrada if validar_data(entrada) else ""
        saida = saida if validar_data(saida) else ""
        bloqueio_auto["ativo"] = True
        try:
            data_matricula_var.set(entrada)
            data_transferencia_var.set(saida)
            ano_var.set((saida or entrada)[-4:])
            serie_var.set(normalizar_serie(registro.get("turma", "")))
            cursando_var.set(not saida and normalizar_texto_busca(registro.get("situacao", "")) == "ATIVO")
        finally:
            bloqueio_auto["ativo"] = False
        on_transfer_date_change()
        return True

    def _valor_booleano_persistido(valor: Any) -> bool:
        if isinstance(valor, bool):
            return valor
        return normalizar_sim_nao(valor) == "sim"

    def aplicar_cache_formulario_da_matricula(matricula: str, atualizar_status: bool = True) -> bool:
        matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
        if len(matricula_norm) != 9:
            return False

        try:
            payload_cache = carregar_cache_formulario_por_matricula(matricula_norm)
        except Exception as exc:
            if atualizar_status:
                status_scan_var.set(f"Falha ao carregar cache do formulario: {exc}")
            return False

        if not payload_cache:
            return False

        dados_cache = payload_cache.get("dados_formulario", {})
        if not isinstance(dados_cache, dict) or not dados_cache:
            return False

        bloqueio_auto["ativo"] = True
        try:
            nome_aluno = str(dados_cache.get("nome_aluno", "") or "").strip()
            if nome_aluno:
                nome_aluno_var.set(nome_aluno)

            ano_var.set(str(dados_cache.get("ano", "") or "").strip())
            nome_escola_var.set(str(dados_cache.get("nome_escola", "") or "").strip())
            cidade_var.set(str(dados_cache.get("cidade", "") or "").strip())
            uf_var.set(str(dados_cache.get("uf", "") or "").strip())
            aplicar_dados_escola_padrao()
            serie_var.set(str(dados_cache.get("serie", "") or "").strip())
            carga_horaria_var.set(str(dados_cache.get("carga_horaria", "") or "").strip())
            data_matricula_var.set(str(dados_cache.get("data_matricula", "") or "").strip())
            data_transferencia_var.set(str(dados_cache.get("data_transferencia", "") or "").strip())

            ja_estudou_var.set(_valor_booleano_persistido(dados_cache.get("ja_estudou", False)))
            ficha_descritiva_var.set(_valor_booleano_persistido(dados_cache.get("ficha_descritiva", False)))
            cursando_var.set(_valor_booleano_persistido(dados_cache.get("cursando", False)))
            deve_historico_var.set(matricula_deve_historico(matricula_norm))
            observacoes_var.set(_valor_booleano_persistido(dados_cache.get("observacoes", False)))
            marcar_disciplinas_var.set(_valor_booleano_persistido(dados_cache.get("marcar_disciplinas", False)))

            definir_texto_observacoes(dados_cache.get("txt_observacoes", ""))
            definir_texto_observacoes_gerais(dados_cache.get("txt_observacoes_gerais", ""))

            arquivos_scan = dados_cache.get("arquivos_scan", [])
            if isinstance(arquivos_scan, list):
                atualizar_campo_arquivos(arquivos_scan)
            elif str(dados_cache.get("arquivo_scan", "") or "").strip():
                atualizar_campo_arquivos(
                    [parte.strip() for parte in re.split(r"\s*\|\s*|\s*;\s*", str(dados_cache.get("arquivo_scan", ""))) if parte.strip()]
                )

            arquivos_documento = dados_cache.get("arquivos_documento", [])
            if isinstance(arquivos_documento, list):
                atualizar_campo_documentos(arquivos_documento)
            elif str(dados_cache.get("arquivo_documento", "") or "").strip():
                atualizar_campo_documentos(
                    [parte.strip() for parte in re.split(r"\s*\|\s*|\s*;\s*", str(dados_cache.get("arquivo_documento", ""))) if parte.strip()]
                )

            for disciplina, var in disciplinas_vars.items():
                var.set(str(dados_cache.get(disciplina, "") or "").strip())

            mostrar_disciplinas()
        finally:
            bloqueio_auto["ativo"] = False

        if (validar_data(data_transferencia_var.get()) or not carga_horaria_var.get().strip()
                or (ano_var.get() == '2026'
                    and normalizar_texto_busca(cidade_var.get()) == 'APARECIDA DE GOIANIA')):
            on_transfer_date_change()

        salvo_em = str(payload_cache.get("salvo_em", "") or "").strip()
        if atualizar_status:
            complemento = f" Cache restaurado de {salvo_em}." if salvo_em else " Cache restaurado."
            status_scan_var.set(
                f"Matricula {matricula_norm} carregada com dados persistidos do formulario.{complemento}"
            )
        return True

    def aplicar_cache_historico_da_matricula(matricula: str, atualizar_status: bool = True) -> bool:
        matricula_norm = re.sub(r"\D", "", str(matricula or "").strip())
        if len(matricula_norm) != 9:
            return False

        try:
            payload_cache = carregar_cache_historico_por_matricula(matricula_norm)
        except Exception as exc:
            if atualizar_status:
                status_scan_var.set(f"Falha ao carregar cache do historico: {exc}")
            return False

        if not payload_cache:
            return False

        resultado_cache = payload_cache.get("resultado_ia", {})
        if not isinstance(resultado_cache, dict) or not resultado_cache:
            return False

        arquivos_cache = payload_cache.get("arquivos_scan", [])
        if isinstance(arquivos_cache, list) and arquivos_cache:
            atualizar_campo_arquivos(arquivos_cache)

        preencher_formulario_com_ia(resultado_cache)
        salvo_em = str(payload_cache.get("salvo_em", "") or "").strip()
        if atualizar_status:
            complemento = f" Cache restaurado de {salvo_em}." if salvo_em else " Cache restaurado."
            status_scan_var.set(
                f"Matricula {matricula_norm} carregada com dados persistidos do historico.{complemento}"
            )
        return True

    def resolver_nome_duplicado_por_matricula(
        matricula: str,
        nomes_encontrados: List[str],
        *,
        exibir_alertas: bool,
        atualizar_status: bool,
    ) -> Optional[str]:
        nomes_validos = [str(nome).strip() for nome in nomes_encontrados if str(nome).strip()]
        nome_digitado = str(nome_aluno_var.get() or "").strip()
        if nome_digitado:
            nome_digitado_norm = normalizar_texto_busca(nome_digitado)
            for nome in nomes_validos:
                if normalizar_texto_busca(nome) == nome_digitado_norm:
                    return nome

        if not nomes_validos:
            if atualizar_status:
                status_scan_var.set(
                    f"Matricula {matricula} duplicada no CSV, sem nomes validos para selecionar."
                )
            if exibir_alertas:
                messagebox.showerror(
                    "Matricula duplicada",
                    (
                        f"A matricula {matricula} aparece mais de uma vez no lista_alunos.csv,\n"
                        "mas nao ha nomes validos associados para selecionar.\n\n"
                        "Corrija o CSV ou informe os dados manualmente."
                    ),
                    parent=root,
                )
            return None

        if not exibir_alertas:
            if atualizar_status:
                status_scan_var.set(
                    f"Matricula {matricula} associada a mais de um nome no CSV. Clique em Buscar para escolher."
                )
            return None

        nome_escolhido = escolher_nome_para_matricula_em_janela(root, matricula, nomes_validos)
        if not nome_escolhido:
            if atualizar_status:
                status_scan_var.set(
                    f"Selecao de nome cancelada para a matricula {matricula}."
                )
            return None
        return nome_escolhido

    def consultar_matricula_digitada(
        *, exibir_alertas: bool = True, atualizar_status: bool = True
    ) -> bool:
        matricula_digitada = re.sub(r"\D", "", str(numero_matricula_var.get() or "").strip())
        if not matricula_digitada:
            if exibir_alertas:
                messagebox.showwarning(
                    "Matricula",
                    "Informe uma matricula valida com 9 digitos.",
                    parent=root,
                )
            return False

        if len(matricula_digitada) != 9:
            if exibir_alertas:
                messagebox.showwarning(
                    "Matricula",
                    "Informe uma matricula valida com 9 digitos.",
                    parent=root,
                )
            return False

        avisou_devedor = avisar_devedor_historico(
            matricula_digitada,
            exibir_alertas=exibir_alertas,
            atualizar_status=atualizar_status,
        )

        if consulta_matricula_estado["ultima_consultada"] == matricula_digitada and nome_aluno_var.get().strip():
            return True

        try:
            caminho_csv = localizar_csv_alunos()
            total_ocorrencias, nomes_encontrados = buscar_nomes_por_matricula_csv(
                caminho_csv, matricula_digitada
            )
        except Exception as exc:
            consulta_matricula_estado["ultima_consultada"] = ""
            if atualizar_status:
                status_scan_var.set(f"Falha ao consultar lista_alunos.csv: {exc}")
            if exibir_alertas:
                messagebox.showerror(
                    "Lista de alunos",
                    f"Nao foi possivel consultar lista_alunos.csv.\n{exc}",
                    parent=root,
                )
            return False

        if total_ocorrencias == 0:
            consulta_matricula_estado["ultima_consultada"] = ""
            if atualizar_status:
                status_scan_var.set(
                    f"Matricula {matricula_digitada} nao encontrada no lista_alunos.csv."
                )
            if exibir_alertas:
                messagebox.showwarning(
                    "Matricula nao encontrada",
                    (
                        f"A matricula {matricula_digitada} nao foi encontrada no lista_alunos.csv.\n"
                        "Informe o nome manualmente ou confira o CSV."
                    ),
                    parent=root,
                )
            return False

        if total_ocorrencias > 1:
            consulta_matricula_estado["ultima_consultada"] = ""
            nome_escolhido = resolver_nome_duplicado_por_matricula(
                matricula_digitada,
                nomes_encontrados,
                exibir_alertas=exibir_alertas,
                atualizar_status=atualizar_status,
            )
            if not nome_escolhido:
                return False
            nome_aluno_var.set(nome_escolhido)
        else:
            nome_aluno_var.set(nomes_encontrados[0])

        nome_encontrado = str(nome_aluno_var.get() or "").strip()
        consulta_matricula_estado["ultima_consultada"] = matricula_digitada
        cache_restaurado = aplicar_cache_formulario_da_matricula(
            matricula_digitada,
            atualizar_status=atualizar_status,
        )
        if not cache_restaurado:
            cache_restaurado = aplicar_cache_historico_da_matricula(
                matricula_digitada,
                atualizar_status=atualizar_status,
            )
        if not cache_restaurado:
            try:
                cache_restaurado = aplicar_cadastro_matricula(matricula_digitada)
            except Exception as exc:
                status_scan_var.set(f"Falha ao carregar cadastro escolar: {exc}")
        if not avisou_devedor:
            avisar_devedor_historico(
                matricula_digitada,
                exibir_alertas=exibir_alertas,
                atualizar_status=atualizar_status,
            )
        if atualizar_status:
            if not cache_restaurado and not avisou_devedor:
                status_scan_var.set(f"Matricula {matricula_digitada} carregada para: {nome_encontrado}.")
        return True

    def on_matricula_confirmada(_event=None):
        consultar_matricula_digitada(exibir_alertas=True, atualizar_status=True)
        return "break"

    def on_matricula_focus_out(_event=None):
        consultar_matricula_digitada(exibir_alertas=False, atualizar_status=True)

    def atualizar_base_alunos(forcar=False):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if not forcar and base_atualizada_hoje(base_dir):
            return
        status_scan_var.set("Atualizando lista de alunos no GEMUL...")
        root.update_idletasks()
        try:
            verificar_espaco(base_dir)
            pagina = _get_base(garantir_sessao_gemul())
            total = atualizar_base_diaria(pagina, base_dir, forcar=forcar)
            cache_csv.update(matriculas=None, nomes=None)
            cache_rel_aluno["registros"] = None
            consulta_matricula_estado["ultima_consultada"] = ""
            status_scan_var.set(f"Base atualizada: {total} registros de alunos.")
        except Exception as exc:
            mensagem = str(exc)
            if "Target page, context or browser has been closed" in mensagem:
                mensagem = "O navegador foi fechado durante a atualizacao. Use RECUPERAR GEMUL e tente novamente."
            elif isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
                mensagem = "O disco ficou sem espaco durante a atualizacao. Libere espaco e tente novamente."
            status_scan_var.set(f"Base nao atualizada: {mensagem}")
            messagebox.showwarning(
                "Atualizacao de alunos",
                f"Nao foi possivel atualizar a lista. A base anterior foi preservada.\n{mensagem}\n"
                "Use ATUALIZAR ALUNOS para tentar novamente.", parent=root,
            )

    def solicitar_matricula_inicial() -> bool:
        while True:
            valor = simpledialog.askstring(
                "Matricula inicial",
                "Informe o numero da matricula para iniciar:",
                parent=root,
            )
            if valor is None:
                status_scan_var.set("Execucao cancelada na etapa de matricula inicial.")
                return False

            matricula_inicial = re.sub(r"\D", "", str(valor))
            if not matricula_inicial:
                messagebox.showwarning(
                    "Matricula",
                    "Informe uma matricula valida (somente numeros).",
                    parent=root,
                )
                continue

            try:
                caminho_csv = localizar_csv_alunos()
                total_ocorrencias, nomes_encontrados = buscar_nomes_por_matricula_csv(
                    caminho_csv, matricula_inicial
                )
            except Exception as exc:
                continuar = messagebox.askyesno(
                    "Lista de alunos",
                    "Nao foi possivel consultar lista_alunos.csv para validar a matricula.\n"
                    f"{exc}\n\nDeseja continuar assim mesmo?",
                    parent=root,
                )
                if not continuar:
                    continue
                numero_matricula_var.set(matricula_inicial)
                status_scan_var.set(f"Matricula inicial informada: {matricula_inicial}.")
                return True

            if total_ocorrencias > 1:
                nome_escolhido = escolher_nome_para_matricula_em_janela(
                    root, matricula_inicial, nomes_encontrados
                )
                if not nome_escolhido:
                    status_scan_var.set(
                        f"Selecao do nome inicial cancelada para a matricula {matricula_inicial}."
                    )
                    continue
                numero_matricula_var.set(matricula_inicial)
                nome_aluno_var.set(nome_escolhido)
                status_scan_var.set(
                    f"Matricula inicial validada no CSV. Nome escolhido: {nome_escolhido}."
                )
                return True

            if total_ocorrencias == 0:
                continuar_sem_csv = messagebox.askyesno(
                    "Matricula nao encontrada",
                    f"A matricula {matricula_inicial} nao foi encontrada no lista_alunos.csv.\n"
                    "Deseja continuar mesmo assim?",
                    parent=root,
                )
                if not continuar_sem_csv:
                    continue
                numero_matricula_var.set(matricula_inicial)
                status_scan_var.set(
                    f"Matricula inicial {matricula_inicial} nao encontrada no CSV; prosseguindo."
                )
                return True

            numero_matricula_var.set(matricula_inicial)
            nome_aluno_var.set(nomes_encontrados[0])
            status_scan_var.set(
                f"Matricula inicial validada no CSV para: {nomes_encontrados[0]}."
            )
            return True

    def preencher_matricula_com_csv(nome_aluno: str) -> bool:
        if not nome_aluno.strip():
            return False

        matriculas_por_nome, nomes_originais = carregar_base_alunos()
        nome_match, opcoes, score = buscar_matriculas_por_nome(nome_aluno, matriculas_por_nome)
        if not opcoes:
            return False

        nome_exibicao = nomes_originais.get(nome_match, nome_aluno)
        matricula_escolhida = escolher_matricula_em_janela(root, nome_exibicao, opcoes)
        if not matricula_escolhida:
            status_scan_var.set("Selecao de matricula cancelada. Informe manualmente.")
            return False

        numero_matricula_var.set(matricula_escolhida)
        if len(opcoes) > 1:
            status_scan_var.set(
                f"Aluno no CSV: {nome_exibicao}. Matricula escolhida: {matricula_escolhida}."
            )
        elif score < 0.999:
            status_scan_var.set(
                f"Aluno no CSV por similaridade ({score:.0%}). Matricula: {matricula_escolhida}."
            )
        return True

    def aplicar_historico_por_ano(ano_selecionado: str) -> bool:
        ano_chave = extrair_ano_4_digitos(ano_selecionado)
        if not ano_chave or ano_chave not in historicos_por_ano:
            return False

        registro = historicos_por_ano[ano_chave]
        bloqueio_auto["ativo"] = True
        try:
            ano_var.set(registro.get("ano", ano_chave))
            if registro.get("nome_escola"):
                nome_escola_var.set(registro["nome_escola"])
            if registro.get("cidade"):
                cidade_var.set(registro["cidade"])
            if registro.get("uf"):
                uf_var.set(registro["uf"])
            aplicar_dados_escola_padrao()

            serie_ia = normalizar_serie(registro.get("serie", ""))
            serie_var.set(serie_ia or registro.get("serie", ""))

            if registro.get("carga_horaria"):
                carga_horaria_var.set(registro["carga_horaria"])
            else:
                carga_horaria_var.set(calcular_carga_horaria())

            texto_obs = str(registro.get("txt_observacoes", "") or "").strip()
            definir_texto_observacoes(texto_obs)
            definir_texto_observacoes_gerais(registro.get("txt_observacoes_gerais", ""))
            observacoes_var.set(bool(texto_obs))
            cursando_var.set(normalizar_sim_nao(registro.get("cursando", "")) == "sim")

            encontrou_nota = False
            for disciplina, chave in mapa_notas_local.items():
                nota = limpar_nota_extraida(registro.get(chave, ""))
                var = obter_var_disciplina(disciplina)
                if var is None:
                    continue
                var.set(nota)
                if nota:
                    encontrou_nota = True
            marcar_disciplinas_var.set(encontrou_nota)
            mostrar_disciplinas()
        finally:
            bloqueio_auto["ativo"] = False

        return True

    def preencher_formulario_com_ia(resultado_ia: Dict[str, Any]):
        definir_texto_observacoes_gerais(resultado_ia.get("txt_observacoes_gerais", ""))
        nome_aluno = str(resultado_ia.get("nome_aluno", "") or "").strip()
        if nome_aluno:
            nome_aluno_var.set(nome_aluno)

        matricula_inicial = re.sub(r"\D", "", str(numero_matricula_var.get() or ""))
        matricula_ia = re.sub(r"\D", "", str(resultado_ia.get("numero_matricula", "") or ""))
        matricula_preenchida = bool(matricula_inicial)
        if nome_aluno and not matricula_preenchida:
            try:
                matricula_preenchida = preencher_matricula_com_csv(nome_aluno)
            except Exception as exc:
                status_scan_var.set(f"Falha ao consultar lista_alunos.csv: {exc}")
                messagebox.showwarning(
                    "Lista de alunos",
                    f"Nao foi possivel consultar lista_alunos.csv:\n{exc}\n\nInforme a matricula manualmente.",
                    parent=root,
                )
        if not matricula_preenchida and matricula_ia:
            numero_matricula_var.set(matricula_ia)

        if resultado_ia.get("nome_escola"):
            nome_escola_var.set(str(resultado_ia.get("nome_escola", "")).strip())
        if resultado_ia.get("cidade"):
            cidade_var.set(str(resultado_ia.get("cidade", "")).strip())
        if resultado_ia.get("uf"):
            uf_var.set(normalizar_texto_busca(str(resultado_ia.get("uf", "")).strip())[:2])
        aplicar_dados_escola_padrao()

        historicos_por_ano.clear()
        historicos_por_ano.update(construir_historicos_por_ano(resultado_ia))
        anos_disponiveis = list(historicos_por_ano.keys())
        ano_combobox["values"] = anos_disponiveis

        if anos_disponiveis:
            ano_preferido = extrair_ano_4_digitos(resultado_ia.get("ano", "")) or anos_disponiveis[0]
            if not aplicar_historico_por_ano(ano_preferido):
                aplicar_historico_por_ano(anos_disponiveis[0])
        else:
            ano_extraido = extrair_ano_4_digitos(resultado_ia.get("ano", ""))
            if ano_extraido:
                ano_var.set(ano_extraido)
            serie_ia = normalizar_serie(str(resultado_ia.get("serie", "") or ""))
            if serie_ia:
                serie_var.set(serie_ia)
            on_transfer_date_change()

    def resumir_documento_extraido(resultado_documento: Dict[str, Any]) -> str:
        partes: List[str] = []
        tipo_documento = str(resultado_documento.get("tipo_documento", "") or "").strip()
        nome_aluno_doc = str(resultado_documento.get("nome_aluno", "") or "").strip()
        data_nascimento = str(resultado_documento.get("data_nascimento", "") or "").strip()
        mae = str(resultado_documento.get("mae", "") or "").strip()
        pai = str(resultado_documento.get("pai", "") or "").strip()
        naturalidade = str(resultado_documento.get("naturalidade", "") or "").strip()
        numero_documento = str(resultado_documento.get("numero_documento", "") or "").strip()

        if tipo_documento:
            partes.append(f"Tipo: {tipo_documento}.")
        if nome_aluno_doc:
            partes.append(f"Nome: {nome_aluno_doc}.")
        if data_nascimento:
            partes.append(f"Nascimento: {data_nascimento}.")
        if mae:
            partes.append(f"Mae: {mae}.")
        if pai:
            partes.append(f"Pai: {pai}.")
        if naturalidade:
            partes.append(f"Naturalidade: {naturalidade}.")
        if numero_documento:
            partes.append(f"Numero: {numero_documento}.")

        if not partes:
            return "Documento lido pela IA, mas sem campos suficientes para resumo."
        return " ".join(partes)

    def classificar_confianca_documento(score: float, possui_registro: bool) -> str:
        if not possui_registro:
            return "sem validacao confiavel"
        if score >= 0.95:
            return "validacao muito forte"
        if score >= 0.80:
            return "validacao forte"
        if score >= 0.60:
            return "validacao razoavel"
        return "validacao fraca"

    def aplicar_resultado_documento(resultado_documento: Dict[str, Any]):
        nome_aluno_doc = str(resultado_documento.get("nome_aluno", "") or "").strip()
        if nome_aluno_doc:
            nome_aluno_var.set(nome_aluno_doc)

        resumo_extracao = resumir_documento_extraido(resultado_documento)
        resumo_final = resumo_extracao

        try:
            registros_rel_aluno = carregar_base_rel_aluno()
            comparacao = comparar_documento_com_rel_aluno(
                resultado_documento,
                registros_rel_aluno,
                matricula_preferencial=numero_matricula_var.get(),
            )
            possui_registro = comparacao.get("registro") is not None
            score = max(0.0, float(comparacao.get("score") or 0.0))
            classificacao = classificar_confianca_documento(score, possui_registro)
            resumo_final = (
                f"Documento analisado com sucesso. "
                f"Resultado da validacao: {classificacao} ({score:.0%}). "
                f"{comparacao['resumo']} "
                f"{resumo_extracao}"
            ).strip()
            status_documento_var.set(
                f"Documento analisado com sucesso. {classificacao.capitalize()} ({score:.0%})."
            )
        except Exception as exc:
            resumo_final = (
                "Documento analisado com sucesso, mas a comparacao com rel_aluno.csv falhou. "
                f"Motivo: {exc}. {resumo_extracao}"
            ).strip()
            status_documento_var.set(
                "Documento analisado com sucesso, mas a comparacao com rel_aluno.csv falhou."
            )

        messagebox.showinfo(
            "Resultado do Documento",
            resumo_final,
            parent=root,
        )

    def carregar_dados_com_ia():
        if ocr_estado["ativo"]:
            return

        caminhos_scan = obter_caminhos_scan()
        if not caminhos_scan:
            carregar_arquivos_historico_automaticamente(solicitar_recorte=False)
            caminhos_scan = obter_caminhos_scan()
            if not caminhos_scan:
                return

        modelo_ia = OCR_IA_MODEL_PADRAO
        try:
            chave_cache_ocr = calcular_chave_cache_ocr_arquivos(
                caminhos_scan,
                recortes_historico_por_arquivo,
                modelo_ia,
            )
            payload_cache_ocr = carregar_cache_ocr_arquivos(chave_cache_ocr)
        except Exception as exc:
            chave_cache_ocr = ""
            payload_cache_ocr = None
            print(f"Falha ao consultar cache OCR por arquivo: {exc}")

        if payload_cache_ocr and isinstance(payload_cache_ocr.get("resultado_ia"), dict):
            resultado_cache = payload_cache_ocr["resultado_ia"]
            salvo_em = str(payload_cache_ocr.get("salvo_em", "") or "").strip()
            preencher_formulario_com_ia(resultado_cache)
            status_scan_var.set(
                f"Leitura IA restaurada do cache local"
                f"{f' de {salvo_em}' if salvo_em else ''}."
            )
            print(f"OCR/IA restaurado do cache local por arquivo ({chave_cache_ocr}).")
            return

        try:
            caminhos_processados, temporarios = preparar_caminhos_para_ocr(
                caminhos_scan,
                recortes_historico_por_arquivo,
            )
        except Exception as exc:
            messagebox.showerror("Recorte OCR", str(exc), parent=root)
            return

        status_scan_var.set(
            f"Lendo {len(caminhos_scan)} arquivo(s) com IA (limite {OCR_IA_TIMEOUT_SEGUNDOS}s)..."
        )
        print(f"Iniciando OCR/IA para {len(caminhos_scan)} arquivo(s) com modelo {modelo_ia}.")
        ocr_estado["ativo"] = True
        ocr_estado["inicio"] = time.time()
        ocr_estado["frame"] = 0
        if progresso_ocr is not None:
            progresso_ocr.start(12)
        if botao_ler_ia is not None:
            botao_ler_ia.state(["disabled"])
        if botao_ler_documento is not None:
            botao_ler_documento.state(["disabled"])
        atualizar_indicador_ocr()
        root.update_idletasks()

        def worker_ia():
            try:
                resultado_ia = extrair_campos_historico_com_openai(caminhos_processados, model=modelo_ia)
            except Exception as exc:
                traceback.print_exc()
                mensagem_erro = str(exc)

                def notificar_erro():
                    finalizar_indicador_ocr("OCR com falha")
                    status_scan_var.set(f"Falha na leitura IA: {mensagem_erro}")
                    messagebox.showerror("Falha na leitura IA", mensagem_erro, parent=root)

                root.after(0, notificar_erro)
                return
            finally:
                for caminho_temporario in temporarios:
                    try:
                        os.remove(caminho_temporario)
                    except Exception:
                        pass

            def aplicar_resultado():
                preencher_formulario_com_ia(resultado_ia)
                matricula_cache = re.sub(r"\D", "", str(numero_matricula_var.get() or resultado_ia.get("numero_matricula", "") or "").strip())
                try:
                    salvar_cache_historico_por_matricula(matricula_cache, resultado_ia, caminhos_scan)
                except Exception as exc:
                    print(f"Falha ao persistir cache do historico para a matricula {matricula_cache}: {exc}")
                try:
                    salvar_cache_ocr_arquivos(chave_cache_ocr, resultado_ia, caminhos_scan, modelo_ia)
                except Exception as exc:
                    print(f"Falha ao persistir cache OCR por arquivo: {exc}")
                if historicos_por_ano:
                    status_scan_var.set(
                        f"Leitura IA concluida ({len(historicos_por_ano)} ano(s) identificado(s), modelo: {modelo_ia})."
                    )
                else:
                    status_scan_var.set(f"Leitura IA concluida com sucesso (modelo: {modelo_ia}).")
                print("OCR/IA concluido com sucesso.")
                finalizar_indicador_ocr("OCR concluido")

            root.after(0, aplicar_resultado)

        threading.Thread(target=worker_ia, daemon=True).start()

    def carregar_documento_com_ia():
        if ocr_estado["ativo"]:
            return

        caminhos_documento = obter_caminhos_documento()
        if not caminhos_documento:
            selecionar_arquivo_documento()
            caminhos_documento = obter_caminhos_documento()
            if not caminhos_documento:
                return

        try:
            caminhos_processados, temporarios = preparar_caminhos_para_ocr(
                caminhos_documento,
                recortes_documento_por_arquivo,
            )
        except Exception as exc:
            messagebox.showerror("Recorte OCR", str(exc), parent=root)
            return

        status_documento_var.set(f"Lendo {len(caminhos_documento)} arquivo(s) de documento com IA...")
        modelo_ia = OCR_IA_MODEL_PADRAO
        print(f"Iniciando OCR/IA para documento civil com modelo {modelo_ia}.")
        ocr_estado["ativo"] = True
        ocr_estado["inicio"] = time.time()
        ocr_estado["frame"] = 0
        if progresso_ocr is not None:
            progresso_ocr.start(12)
        if botao_ler_ia is not None:
            botao_ler_ia.state(["disabled"])
        if botao_ler_documento is not None:
            botao_ler_documento.state(["disabled"])
        atualizar_indicador_ocr()
        root.update_idletasks()

        def worker_documento():
            try:
                resultado_documento = extrair_campos_documento_civil_com_openai(
                    caminhos_processados,
                    model=modelo_ia,
                )
            except Exception as exc:
                traceback.print_exc()
                mensagem_erro = str(exc)

                def notificar_erro():
                    finalizar_indicador_ocr("OCR com falha")
                    status_documento_var.set(f"Falha na leitura do documento: {mensagem_erro}")
                    messagebox.showerror("Falha na leitura do documento", mensagem_erro, parent=root)

                root.after(0, notificar_erro)
                return
            finally:
                for caminho_temporario in temporarios:
                    try:
                        os.remove(caminho_temporario)
                    except Exception:
                        pass

            def aplicar_resultado_documento_ui():
                aplicar_resultado_documento(resultado_documento)
                print("Leitura do documento civil concluida com sucesso.")
                finalizar_indicador_ocr("OCR concluido")

            root.after(0, aplicar_resultado_documento_ui)

        threading.Thread(target=worker_documento, daemon=True).start()

    root.grid_columnconfigure(1, weight=1)
    root.grid_columnconfigure(3, weight=1)
    root.grid_columnconfigure(4, weight=1)
    root.grid_columnconfigure(5, weight=1)
    root.grid_rowconfigure(8, weight=1)

    ttk.Label(root, text="Número da Matrícula:").grid(row=0, column=0, padx=10, pady=5)
    frame_matricula = ttk.Frame(root)
    frame_matricula.grid(row=0, column=1, padx=10, pady=5, sticky="we")
    frame_matricula.grid_columnconfigure(0, weight=1)
    entrada_matricula = ttk.Entry(frame_matricula, textvariable=numero_matricula_var)
    entrada_matricula.grid(row=0, column=0, sticky="we")
    ttk.Button(frame_matricula, text="Buscar", command=consultar_matricula_digitada).grid(row=0, column=1, padx=(6, 0))
    ttk.Label(root, text="Nome do Aluno (IA):").grid(row=0, column=2, padx=10, pady=5, sticky="e")
    ttk.Entry(root, textvariable=nome_aluno_var, width=45).grid(row=0, column=3, padx=10, pady=5, columnspan=3, sticky="we")

    ttk.Label(root, text="Ano:").grid(row=1, column=0, padx=10, pady=5)
    ano_combobox = ttk.Combobox(root, textvariable=ano_var)
    ano_combobox.grid(row=1, column=1, padx=10, pady=5, sticky="we")
    ttk.Label(root, text="Arquivo(s) do Historico:").grid(row=1, column=2, padx=10, pady=5, sticky="e")
    ttk.Entry(root, textvariable=arquivo_scan_var, width=45).grid(row=1, column=3, padx=10, pady=5, sticky="we")
    ttk.Button(root, text="Arquivos...", command=selecionar_arquivo_scan).grid(row=1, column=4, padx=5, pady=5)
    botao_ler_ia = ttk.Button(root, text="Ler com IA", command=carregar_dados_com_ia)
    botao_ler_ia.grid(row=1, column=5, padx=5, pady=5)
    tk.Label(root, textvariable=status_scan_var, anchor="w", justify="left", wraplength=520).grid(
        row=2, column=3, columnspan=3, padx=10, pady=2, sticky="w"
    )

    ttk.Label(root, text="Arquivo(s) do Documento:").grid(row=3, column=2, padx=10, pady=5, sticky="e")
    ttk.Entry(root, textvariable=arquivo_documento_var, width=45).grid(row=3, column=3, padx=10, pady=5, sticky="we")
    ttk.Button(root, text="Documento...", command=selecionar_arquivo_documento).grid(row=3, column=4, padx=5, pady=5)
    botao_ler_documento = ttk.Button(root, text="Ler Documento", command=carregar_documento_com_ia)
    botao_ler_documento.grid(row=3, column=5, padx=5, pady=5)

    ttk.Label(root, text="Nome da Escola:").grid(row=3, column=0, padx=10, pady=5)
    escola_combobox = ttk.Combobox(root, textvariable=nome_escola_var, values=ESCOLAS_SUGERIDAS)
    escola_combobox.grid(row=3, column=1, padx=10, pady=5, sticky="we")

    tk.Label(root, textvariable=status_documento_var, anchor="w", justify="left", wraplength=360).grid(
        row=4, column=4, columnspan=2, padx=10, pady=2, sticky="w"
    )

    ttk.Label(root, text="Cidade:").grid(row=4, column=0, padx=10, pady=5)
    ttk.Entry(root, textvariable=cidade_var).grid(row=4, column=1, padx=10, pady=5, sticky="we")
    ttk.Label(root, text="UF:").grid(row=4, column=2, padx=10, pady=5)
    ttk.Entry(root, textvariable=uf_var).grid(row=4, column=3, padx=10, pady=5, sticky="we")

    tk.Checkbutton(root, text="Cursando", variable=cursando_var).grid(row=5, column=2, padx=10, pady=5, sticky="w")
    tk.Checkbutton(root, text="Ficha Descritiva", variable=ficha_descritiva_var).grid(row=5, column=3, padx=10, pady=5)
    tk.Checkbutton(root, text="Já estudou aqui", variable=ja_estudou_var).grid(row=5, column=4, padx=10, pady=5, sticky="w")
    tk.Checkbutton(root, text="Deve histórico", variable=deve_historico_var, command=salvar_deve_historico_atual).grid(
        row=5, column=5, padx=10, pady=5, sticky="w"
    )

    ttk.Label(root, text="Série:").grid(row=5, column=0, padx=10, pady=5)
    serie_combobox = ttk.Combobox(root, textvariable=serie_var)
    serie_combobox["values"] = series
    serie_combobox.grid(row=5, column=1, padx=10, pady=5, sticky="we")
    serie_combobox.bind("<KeyRelease>", autocomplete)

    ttk.Label(root, text="Carga Horária:").grid(row=6, column=0, padx=10, pady=5)
    ttk.Entry(root, textvariable=carga_horaria_var).grid(row=6, column=1, padx=10, pady=5, sticky="we")
    ttk.Label(root, text="Data de Transferência:").grid(row=6, column=2, padx=10, pady=5)
    ttk.Entry(root, textvariable=data_transferencia_var).grid(row=6, column=3, padx=10, pady=5, sticky="we")
    ttk.Label(root, textvariable=ocr_timer_var).grid(row=6, column=4, columnspan=2, padx=10, pady=2, sticky="w")

    tk.Checkbutton(root, text="Observações", variable=observacoes_var).grid(row=7, column=0, padx=10, pady=5, sticky="w")
    ttk.Label(root, text="Texto de Observações:").grid(row=7, column=2, padx=10, pady=5, sticky="w")
    progresso_ocr = ttk.Progressbar(root, mode="indeterminate", length=240)
    progresso_ocr.grid(row=7, column=4, columnspan=2, padx=10, pady=2, sticky="we")

    obs_frame = ttk.Frame(root)
    obs_frame.grid(row=8, column=2, columnspan=4, rowspan=12, padx=10, pady=5, sticky="nsew")
    obs_frame.grid_columnconfigure(0, weight=1)
    obs_frame.grid_rowconfigure(0, weight=1)

    ttk.Label(obs_frame, text="Observação do ano:").grid(row=0, column=0, sticky="w")
    txt_observacoes_widget = tk.Text(obs_frame, wrap="word", height=6)
    txt_observacoes_widget.grid(row=1, column=0, sticky="nsew")
    obs_scroll = ttk.Scrollbar(obs_frame, orient="vertical", command=txt_observacoes_widget.yview)
    obs_scroll.grid(row=1, column=1, sticky="ns")
    txt_observacoes_widget.configure(yscrollcommand=obs_scroll.set)
    txt_observacoes_widget.bind("<KeyRelease>", on_observacoes_text_change)
    ttk.Label(obs_frame, text="Observação geral:").grid(row=2, column=0, sticky="w")
    txt_observacoes_gerais_widget = tk.Text(obs_frame, wrap="word", height=6)
    txt_observacoes_gerais_widget.grid(row=3, column=0, sticky="nsew")
    obs_gerais_scroll = ttk.Scrollbar(obs_frame, orient="vertical", command=txt_observacoes_gerais_widget.yview)
    obs_gerais_scroll.grid(row=3, column=1, sticky="ns")
    txt_observacoes_gerais_widget.configure(yscrollcommand=obs_gerais_scroll.set)
    obs_frame.grid_rowconfigure(0, weight=0)
    obs_frame.grid_rowconfigure(1, weight=1)
    obs_frame.grid_rowconfigure(3, weight=1)

    tk.Checkbutton(root, text="Marcar Disciplinas", variable=marcar_disciplinas_var, command=mostrar_disciplinas).grid(
        row=8, column=0, padx=10, pady=5, sticky="w"
    )

    for indice, (disciplina, var) in enumerate(disciplinas_vars.items(), start=9):
        label_widget = ttk.Label(root, text=disciplina + ":")
        entry_widget = ttk.Entry(root, textvariable=var)
        label_widget.grid(row=indice, column=0, padx=10, pady=5, sticky="e")
        entry_widget.grid(row=indice, column=1, padx=10, pady=5, sticky="we")
        label_widget.grid_remove()
        entry_widget.grid_remove()
        disciplina_widgets.append((label_widget, entry_widget))

    ttk.Checkbutton(root, text='Gerar cobrança de histórico', variable=gerar_cobranca_var,
                    command=abrir_cobranca_historico).grid(
        row=18, column=0, columnspan=2, padx=10, pady=5, sticky='w')

    def encerrar_aplicacao():
        monitoramento_navegador["ativo"] = False
        monitoramento_navegador["encerrando"] = True
        try:
            FuncoesDoPrograma.finalizar_navegador()
        except Exception:
            traceback.print_exc()
        try:
            root.quit()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass
        encerrar_processo_imediatamente(0)

    def verificar_fechamento_manual_do_navegador():
        if not monitoramento_navegador["ativo"] or monitoramento_navegador["encerrando"]:
            return

        try:
            navegador_inicializado = bool(sessao_execucao.get("navegador_inicializado"))
            navegador_ativo = navegador_playwright_ativo()
        except Exception:
            navegador_inicializado = False
            navegador_ativo = False

        if navegador_inicializado and not navegador_ativo:
            mensagem = "Navegador fechado manualmente. Use RECUPERAR GEMUL ou OK para abrir outra sessao."
            print(mensagem)
            FuncoesDoPrograma.finalizar_navegador()
            try:
                status_scan_var.set(mensagem)
            except Exception:
                pass

        try:
            root.after(1000, verificar_fechamento_manual_do_navegador)
        except Exception:
            monitoramento_navegador["ativo"] = False

    botao_ok = ttk.Button(root, text="OK", command=submit)
    botao_ok.grid(row=21, column=0, columnspan=2, pady=10)
    ttk.Button(root, text="CANCELAR", command=encerrar_aplicacao).grid(row=21, column=2, columnspan=2, pady=10)
    ttk.Button(root, text="RECUPERAR GEMUL", command=recuperar_gemul).grid(row=21, column=4, columnspan=2, pady=10)
    ttk.Button(root, text="RESET", command=resetar_formulario).grid(row=22, column=0, columnspan=6, pady=(0, 10))
    ttk.Button(root, text="ATUALIZAR ALUNOS", command=lambda: atualizar_base_alunos(forcar=True)).grid(
        row=23, column=0, columnspan=6, pady=(0, 10))
    root.protocol("WM_DELETE_WINDOW", encerrar_aplicacao)

    entrada_frame = ttk.Frame(root)
    entrada_frame.grid(row=7, column=1, padx=10, pady=5, sticky="we")
    ttk.Label(entrada_frame, text="Entrada:").pack(side="left")
    ttk.Entry(entrada_frame, textvariable=data_matricula_var, width=12).pack(side="left", fill="x", expand=True)
    data_matricula_var.trace_add("write", on_transfer_date_change)
    data_transferencia_var.trace_add("write", on_transfer_date_change)
    nome_escola_var.trace_add("write", on_escola_change)
    cidade_var.trace_add("write", on_cidade_change)
    serie_var.trace_add("write", on_serie_change)
    ano_var.trace_add("write", on_ano_change)
    escola_combobox.bind("<<ComboboxSelected>>", on_escola_change)
    ano_combobox.bind("<<ComboboxSelected>>", on_ano_change)
    entrada_matricula.bind("<Return>", on_matricula_confirmada)
    entrada_matricula.bind("<FocusOut>", on_matricula_focus_out)

    aplicar_dados_escola_padrao()
    on_transfer_date_change()

    carregar_arquivos_historico_automaticamente(solicitar_recorte=False)

    atualizar_base_alunos()

    if not solicitar_matricula_inicial():
        root.destroy()
        return dados

    if not aplicar_cache_formulario_da_matricula(numero_matricula_var.get(), atualizar_status=True):
        aplicar_cache_historico_da_matricula(numero_matricula_var.get(), atualizar_status=True)
    if not ano_var.get() or not serie_var.get():
        try:
            aplicar_cadastro_matricula(numero_matricula_var.get())
        except Exception as exc:
            status_scan_var.set(f"Falha ao carregar cadastro escolar: {exc}")
    avisar_devedor_historico(
        numero_matricula_var.get(),
        exibir_alertas=True,
        atualizar_status=True,
    )

    root.deiconify()
    maximizar_janela_tk(root)
    root.lift()
    root.focus_force()
    root.after(1000, verificar_fechamento_manual_do_navegador)

    root.mainloop()
    root.destroy()
    return dados

class ProcessamentoDeObservacoes:

    def _eh_primeiro_ou_segundo_ano(self, serie):
        return normalizar_serie(serie) in {
            f"1{ORDINAL_INDICATOR} ANO",
            f"2{ORDINAL_INDICATOR} ANO",
        }

    def _eh_agrupamento_quatro_ou_cinco(self, serie):
        return normalizar_serie(serie) in {
            "AGRUPAMENTO 4",
            "AGRUPAMENTO 5",
        }

    def _eh_jardim_bela_vista_aparecida(self, escola, cidade):
        return (
            normalizar_texto_busca(escola) == "ESCOLA MUNICIPAL JARDIM BELA VISTA"
            and normalizar_texto_busca(cidade) == "APARECIDA DE GOIANIA"
        )

    def _matricula_atual(self) -> str:
        return re.sub(r"\D", "", str(sessao_execucao.get("matricula_atual", "") or "").strip())

    def _resolucao_011_completa_ja_exibida(self) -> bool:
        matricula = self._matricula_atual()
        if not matricula:
            return False
        exibidas = sessao_execucao.get("resolucao_011_completa_por_matricula", set())
        return matricula in exibidas

    def _marcar_resolucao_011_completa_exibida(self) -> None:
        matricula = self._matricula_atual()
        if not matricula:
            return
        exibidas = sessao_execucao.setdefault("resolucao_011_completa_por_matricula", set())
        exibidas.add(matricula)

    def _aplicar_resumo_resolucao_011_se_repetida(self, texto):
        possui_texto_longo = (
            APARECIDA_RESOLUCAO_011_TEXTO_BASE in texto
            or APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO in texto
        )
        if not possui_texto_longo:
            return texto

        if self._resolucao_011_completa_ja_exibida():
            texto = texto.replace(
                APARECIDA_RESOLUCAO_011_TEXTO_BASE,
                APARECIDA_RESOLUCAO_011_TEXTO_RESUMO,
                1,
            )
            texto = texto.replace(
                APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO,
                APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO_RESUMO,
                1,
            )
            return texto

        self._marcar_resolucao_011_completa_exibida()
        return texto

    def _aplicar_observacao_primeiro_segundo_ano_aparecida(self, texto, serie):
        if not self._eh_primeiro_ou_segundo_ano(serie):
            return texto
        if APARECIDA_OBSERVACAO_1O_2O_ANO.strip() in texto:
            return texto

        trechos_base = (
            APARECIDA_RESOLUCAO_011_TEXTO_BASE,
            APARECIDA_RESOLUCAO_011_TEXTO_RESUMO,
            APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO,
            APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO_RESUMO,
            APARECIDA_REANP_2020_TEXTO_BASE,
            APARECIDA_RESOLUCAO_011_TEXTO_CURTO,
        )
        if not any(trecho_base in texto for trecho_base in trechos_base):
            return texto

        for trecho_ficha in (
            " Aluno(a) avaliado(a) atrav\u00e9s de Ficha Descritiva em anexo.",
            " Aluno(a) avaliado(a) atrav\u00e9s de Ficha Descritiva, em anexo.",
        ):
            if trecho_ficha in texto:
                return texto.replace(trecho_ficha, APARECIDA_OBSERVACAO_1O_2O_ANO, 1)

        for trecho_base in trechos_base:
            if trecho_base in texto:
                return texto.replace(
                    trecho_base,
                    trecho_base + APARECIDA_OBSERVACAO_1O_2O_ANO,
                    1,
                )

        return texto

    def _aplicar_observacao_agrupamento_aparecida(self, texto, serie, escola, cidade):
        if not self._eh_agrupamento_quatro_ou_cinco(serie):
            return texto
        if not self._eh_jardim_bela_vista_aparecida(escola, cidade):
            return texto
        if APARECIDA_OBSERVACAO_AGRUPAMENTO_4_5.strip() in texto:
            return texto

        trechos_base = (
            APARECIDA_RESOLUCAO_011_TEXTO_BASE,
            APARECIDA_RESOLUCAO_011_TEXTO_RESUMO,
            APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO,
            APARECIDA_RESOLUCAO_011_TRECHO_SEM_PREFIXO_RESUMO,
            APARECIDA_REANP_2020_TEXTO_BASE,
            APARECIDA_RESOLUCAO_011_TEXTO_CURTO,
        )
        if not any(trecho_base in texto for trecho_base in trechos_base):
            return texto

        for trecho_ficha in (
            " Aluno(a) avaliado(a) atrav\u00e9s de Ficha Descritiva em anexo.",
            " Aluno(a) avaliado(a) atrav\u00e9s de Ficha Descritiva, em anexo.",
        ):
            if trecho_ficha in texto:
                return texto.replace(trecho_ficha, APARECIDA_OBSERVACAO_AGRUPAMENTO_4_5, 1)

        for trecho_base in trechos_base:
            if trecho_base in texto:
                return texto.replace(
                    trecho_base,
                    trecho_base + APARECIDA_OBSERVACAO_AGRUPAMENTO_4_5,
                    1,
                )

        return texto
    
    def decisao_texto(self, ano, escola, cidade, ja_estudou, ficha_descritiva, observacoes, serie):
        ano = int(exigir_ano_4_digitos(ano))  # Converte o ano para inteiro
        ano_corrente = datetime.now().year
        escola = normalizar_texto_busca(escola)
        cidade = normalizar_texto_busca(cidade)
        observacoes = corrigir_texto_utf8(observacoes)
        serie = corrigir_texto_utf8(serie)
        
        # Condição para ano menor que 2019
        if ano < 2019:
            texto = self.processa_ano_menor_2019(escola, cidade, ja_estudou, ficha_descritiva, observacoes)

        # Condição para ano igual a 2020
        elif ano == 2020:
            texto = self.processa_ano_2020(escola, cidade, ja_estudou, ficha_descritiva, observacoes)

        # Condição para ano igual a 2021
        elif ano == 2021:
            texto = self.processa_ano_2021(escola, cidade, ja_estudou, ficha_descritiva, observacoes)

        # Condição para o ano corrente
        elif ano == ano_corrente:
            texto = self.processa_ano_corrente(escola, cidade, ja_estudou, ficha_descritiva, observacoes, serie)

        # Condição para qualquer outro ano
        else:
            texto = self.processa_ano_padrao(escola, cidade, ja_estudou, ficha_descritiva, observacoes)

        texto = corrigir_texto_utf8(texto)
        texto = self._aplicar_resumo_resolucao_011_se_repetida(texto)
        texto = self._aplicar_observacao_primeiro_segundo_ano_aparecida(texto, serie)
        return self._aplicar_observacao_agrupamento_aparecida(texto, serie, escola, cidade)
    
    def processa_ano_menor_2019(self, escola, cidade, ja_estudou, ficha_descritiva, observacoes):
        # Condição 1: Se 'escola' for 'ESCOLA MUNICIPAL JARDIM BELA VISTA'
        if escola == "ESCOLA MUNICIPAL JARDIM BELA VISTA":
            if ja_estudou == "nao":
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução Normativa 005/07 CME de Aparecida de Goiânia-GO. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução Normativa 005/07 CME de Aparecida de Goiânia-GO."
            else:  # ja_estudou == "sim"
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução Normativa 005/07 CME. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução Normativa 005/07 CME de Aparecida de Goiânia-GO."
        
        else:
            if cidade == "APARECIDA DE GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução Normativa 005/07 CME de Aparecida de Goiânia-GO. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução Normativa 005/07 CME de Aparecida de Goiânia-GO. Histórico transcrito conforme o original."
                else:  # ja_estudou == "sim"
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução 005/07. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução 005/07. Histórico transcrito conforme o original."
            
            elif cidade == "GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return ("Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada "
                                "através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Histórico transcrito conforme o original.")
                    else:
                        return "Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano. Histórico transcrito conforme o original."
                else:  # ja_estudou == "sim"
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266. Histórico transcrito conforme o original."
            
            else:  # cidade != "GOIANIA"
                if observacoes:  # Verifica se observacoes é True
                    return f"{observacoes} Histórico transcrito conforme o original."
        
        return "Nenhuma observação. Histórico transcrito conforme o original"

    # Métodos placeholders para os outros anos, a serem implementados conforme necessário
    def processa_ano_2020(self, escola, cidade, ja_estudou, ficha_descritiva, observacoes):
        if escola == "ESCOLA MUNICIPAL JARDIM BELA VISTA":
            if ja_estudou == "nao":
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia."
            else:
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia."
        else:
            if cidade == "APARECIDA DE GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia. Histórico transcrito conforme o original."
                else:
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Aprovado(a) conforme Resolução CME nº 014, de 01 de outubro de 2020, que dispõe sobre a aprovação automática dos alunos devidamente matriculados na Rede Municipal de Ensino de Aparecida de Goiânia. Histórico transcrito conforme o original."
            elif cidade == "GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Histórico transcrito conforme o original."
                else:
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva, no entanto tal documento não se fez presente anexo ao documento recebido. Histórico transcrito conforme o original."
            else:
                if observacoes:
                    return f"{observacoes} Histórico transcrito conforme o original."
        return "Nenhuma observação. Histórico transcrito conforme o original."

    def processa_ano_2021(self, escola, cidade, ja_estudou, ficha_descritiva, observacoes):
        if escola == "ESCOLA MUNICIPAL JARDIM BELA VISTA":
            if ja_estudou == "nao":
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia."
            else:
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução 011/2019. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução 011/2019."
        else:
            if cidade == "APARECIDA DE GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Histórico transcrito conforme o original."
                else:
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução 011/2019. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução nº 004/2020 Dispõe sobre o regime especial de aulas não presenciais (REANP) no Sistema de Ensino do município de Aparecida de Goiânia, como medida preventiva à disseminação do COVID-19. Resolução 011/2019. Histórico transcrito conforme o original."
            elif cidade == "GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08, compreendendo os períodos da infância = Ciclo I / pré-adolescência = Ciclo II / adolescência = Ciclo III. Componentes curriculares: Arte, Ciência, Educação Física, Geografia, História, Língua Estrangeira Moderna Inglês, Língua Portuguesa e Matemática. Carga horária anual: 800 / dias letivos: 200. Nos ciclos, a avaliação é descritiva, em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08, compreendendo os períodos da infância = Ciclo I / pré-adolescência = Ciclo II / adolescência = Ciclo III. Componentes curriculares: Arte, Ciência, Educação Física, Geografia, História, Língua Estrangeira Moderna Inglês, Língua Portuguesa e Matemática. Carga horária anual: 800 / dias letivos: 200. Nos ciclos, a avaliação é descritiva, no entanto tal documento não se fez presente anexo ao documento recebido. Histórico transcrito conforme o original."
                else:
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva, em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva, no entanto tal documento não se fez presente anexo ao documento recebido. Histórico transcrito conforme o original."
            else:
                if observacoes:
                    return f"{observacoes} Histórico transcrito conforme o original."
        return "Nenhuma observação. Histórico transcrito conforme o original."

    def processa_ano_corrente(self, escola, cidade, ja_estudou, ficha_descritiva, observacoes, serie):
        if escola == "ESCOLA MUNICIPAL JARDIM BELA VISTA":
            if ja_estudou == "nao":
                if ficha_descritiva == "sim":
                    return f"Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                else:
                    return f"Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
            else:
                if ficha_descritiva == "sim":
                    return f"Aluno(a) avaliado(a) conforme a Resolução 011/2019. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                else:
                    return f"Aluno(a) avaliado(a) conforme a Resolução 011/2019. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
        else:
            if cidade == "APARECIDA DE GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return f"Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                    else:
                        return f"Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                else:
                    if ficha_descritiva == "sim":
                        return f"Aluno(a) avaliado(a) conforme a Resolução 011/2019. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                    else:
                        return f"Aluno(a) avaliado(a) conforme a Resolução 011/2019. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
            elif cidade == "GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return f"Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08, compreendendo os períodos da infância = Ciclo I / pré-adolescência = Ciclo II / adolescência = Ciclo III. Componentes curriculares: Arte, Ciência, Educação Física, Geografia, História, Língua Estrangeira Moderna Inglês, Língua Portuguesa e Matemática. Carga horária anual: 800 / dias letivos: 200. Nos ciclos, a avaliação é descritiva, em anexo. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                    else:
                        return f"Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08, compreendendo os períodos da infância = Ciclo I / pré-adolescência = Ciclo II / adolescência = Ciclo III. Componentes curriculares: Arte, Ciência, Educação Física, Geografia, História, Língua Estrangeira Moderna Inglês, Língua Portuguesa e Matemática. Carga horária anual: 800 / dias letivos: 200. Nos ciclos, a avaliação é descritiva, no entanto tal documento não se fez presente anexo ao documento recebido. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                else:
                    if ficha_descritiva == "sim":
                        return f"Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva, em anexo. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
                    else:
                        return f"Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva, no entanto tal documento não se fez presente anexo ao documento recebido. Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
            else:
                if observacoes:
                    return f"{observacoes} Histórico transcrito conforme o original. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."
        return f"Texto padrão para o ano corrente. Aluno(a) apto(a) a dar continuidade aos estudos no {serie}."

    def processa_ano_padrao(self, escola, cidade, ja_estudou, ficha_descritiva, observacoes):
        if escola == "ESCOLA MUNICIPAL JARDIM BELA VISTA":
            if ja_estudou == "nao":
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia."
            else:
                if ficha_descritiva == "sim":
                    return "Aluno(a) avaliado(a) conforme a Resolução 011/2019. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo."
                else:
                    return "Aluno(a) avaliado(a) conforme a Resolução 011/2019."
        else:
            if cidade == "APARECIDA DE GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução CME nº. 011, de 25 de novembro de 2019, que estabelece diretrizes e normas para as etapas e modalidades da Educação Básica e procedimentos para credenciamento, recredenciamento, autorização e renovação de funcionamento de instituições educacionais do Sistema Municipal de Ensino de Aparecida de Goiânia. Histórico transcrito conforme o original."
                else:
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resolução 011/2019. Aluno(a) avaliado(a) através de Ficha Descritiva, em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resolução 011/2019. Histórico transcrito conforme o original."
            elif cidade == "GOIANIA":
                if ja_estudou == "nao":
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29-05-98 e CME/Goiânia nº 1240/08."  # Alterei as barras

                    else:
                        return "Sem observações. Histórico transcrito conforme original" #Aluno(a) avaliado(a) conforme a Proposta pedagógica Ciclos de Formação e Desenvolvimento Humano, regulamentada através das resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08, compreendendo os períodos da infância = Ciclo I / pré-adolescência = Ciclo II / adolescência = Ciclo III. Componentes curriculares: Arte, Ciência, Educação Física, Geografia, História, Língua Estrangeira Moderna Inglês, Língua Portuguesa e Matemática. Carga horária anual: 800 / dias letivos: 200. Nos ciclos, a avaliação é descritiva, no entanto tal documento não se fez presente anexo ao documento recebido. Histórico transcrito conforme o original."
                else:
                    if ficha_descritiva == "sim":
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva, em anexo. Histórico transcrito conforme o original."
                    else:
                        return "Aluno(a) avaliado(a) conforme a Resoluções CEE/GO nº 266, de 29/05/98 e CME/Goiânia nº 1240/08. Nos ciclos, a avaliação é descritiva, no entanto tal documento não se fez presente anexo ao documento recebido. Histórico transcrito conforme o original."
            else:
                if observacoes:
                    return f"{observacoes} Histórico transcrito conforme o original."
        return "Nenhuma observação. Histórico transcrito conforme o original."

def escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, txt_observacoes_gerais=""):
    # Cria uma instÃ¢ncia da classe ProcessamentoDeObservacoes
    processamento = ProcessamentoDeObservacoes()
    
    # Chama a funÃ§Ã£o decisao_texto para gerar o texto baseado nas condiÃ§Ãµes
    observacoes_geradas = processamento.decisao_texto(ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie)
    observacoes_geradas = mesclar_textos_observacao(corrigir_texto_utf8(observacoes_geradas), txt_observacoes)
    
    # Adiciona um print para verificar o texto gerado
    print(f"Texto gerado para observaÃ§Ãµes: {observacoes_geradas}")
    
    # Escreve o valor da variÃ¡vel 'carga_horaria' na caixa de texto '//*[@id="txtCHTotal"]'
    FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCHTotal"]', carga_horaria)
    
    # Verifica se o campo de observaÃ§Ãµes estÃ¡ disponÃ­vel antes de escrever o texto
    texto_geral = corrigir_texto_utf8(txt_observacoes_gerais or "").strip()
    if texto_geral:
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtObservacaoGeral"]', texto_geral)

    try:
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtObservacao"]', observacoes_geradas)
        print("Texto escrito com sucesso no campo de observaÃ§Ãµes.")
    except Exception as e:
        print(f"Erro ao escrever no campo de observaÃ§Ãµes: {e}")
def definir_media_pela_disciplina(driver, disciplina_selecionada, notas):
    try:
        disciplina_elemento = driver.locator('xpath=//*[@id="cmbDisciplina"]')
        disciplina_elemento.wait_for(state="attached", timeout=10000)
        driver.wait_for_timeout(200)

        disciplina_elemento.select_option(label=disciplina_selecionada, force=True)

        print(f"Disciplina '{disciplina_selecionada}' selecionada com sucesso.")
        media_elemento = driver.locator('xpath=//*[@id="txtMedia"]')
        media_elemento.wait_for(state="attached", timeout=10000)
        driver.wait_for_timeout(200)

        if disciplina_selecionada in ["1Âº MOMENTO", "2Âº MOMENTO"]:
            media_elemento.fill("0")
            print("Media '0' definida para '1Âº MOMENTO' ou '2Âº MOMENTO'.")
        else:
            media = notas.get(disciplina_selecionada, "0")
            media_elemento.fill(str(media))
            print(f"Media '{media}' definida para a disciplina '{disciplina_selecionada}'.")
    except Exception as e:
        print(f"Erro ao definir a media para a disciplina '{disciplina_selecionada}': {e}")

def combo_cadastramento_dados(driver, ano, nome_escola, cidade, uf, carga_horaria, txt_observacoes, serie, ja_estudou, ficha_descritiva):
    # Chama a funÃ§Ã£o decisao_texto para gerar o texto baseado nas condiÃ§Ãµes
    observacoes_geradas = decisao_texto(ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie)
    
    # Adiciona um print para verificar o texto gerado
    print(f"Texto gerado para observaÃ§Ãµes: {observacoes_geradas}")

    # Escreve o valor da variÃ¡vel 'carga_horaria' na caixa de texto '//*[@id="txtCHTotal"]'
    FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCHTotal"]', carga_horaria)

    # Verifica se o campo de observaÃ§Ãµes estÃ¡ disponÃ­vel antes de escrever o texto
    try:
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtObservacao"]', observacoes_geradas)
        print("Texto escrito com sucesso no campo de observaÃ§Ãµes.")
    except Exception as e:
        print(f"Erro ao escrever no campo de observaÃ§Ãµes: {e}")


    # Seleciona a opÃ§Ã£o no item de xpath '//*[@id="cmbSituacaoPromocao"]'
    situacao_elemento = driver.find_element(By.XPATH, '//*[@id="cmbSituacaoPromocao"]')
    situacao_elemento.click()
    situacao_elemento.find_element(By.XPATH, "//option[text()='Aprovado']").click()


    # Marca o checkbox no item de xpath '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input'
    FuncoesDoPrograma.marcar_checkbox(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input')

    # Escreve zero (0) na caixa de texto '//*[@id="txtMedia"]'
    FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtMedia"]', '0')

    # Chama funÃ§Ãµes end() e incluir_enviar_dados(driver)
    
    FuncoesDoPrograma.incluir_enviar_dados(driver)
    
    # Segundo bloco de repetiÃ§Ã£o
    
    # Seleciona a opÃ§Ã£o no item de xpath '//*[@id="cmbCurso"]'
    curso_elemento = driver.find_element(By.XPATH, '//*[@id="cmbCurso"]')
    curso_elemento.click()
    curso_elemento.find_element(By.XPATH, "//option[text()='EI-EDUCAÃ‡ÃƒO INFANTIL']").click()
    
    # Ajusta janela para item estar interÃ¡vel
    Atalho.pagedown()

    # Seleciona a opÃ§Ã£o no item de xpath '//*[@id="cmbPeriodo"]'
    periodo_elemento = driver.find_element(By.XPATH, '//*[@id="cmbPeriodo"]')
    periodo_elemento.click()
    periodo_elemento.find_element(By.XPATH, "//option[text()='AGRUPAMENTO IV']").click()

    # Seleciona a opÃ§Ã£o no item de xpath '//*[@id="cmbDisciplina"]'
    disciplina_elemento = driver.find_element(By.XPATH, '//*[@id="cmbDisciplina"]')
    disciplina_elemento.click()
    disciplina_elemento.find_element(By.XPATH, "//option[text()='1Âº MOMENTO']").click()

    # Seleciona a opÃ§Ã£o no item de xpath '//*[@id="cmbSituacaoPromocao"]'
    situacao_elemento = driver.find_element(By.XPATH, '//*[@id="cmbSituacaoPromocao"]')
    situacao_elemento.click()
    situacao_elemento.find_element(By.XPATH, "//option[text()='Aprovado']").click()

    FuncoesDoPrograma.marcar_checkbox(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input')
    FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtMedia"]', '0')
    
    FuncoesDoPrograma.incluir_enviar_dados(driver)
    
    # Segundo bloco de repetiÃ§Ã£o
    # Segundo bloco de repetiÃ§Ã£o
    curso_elemento = driver.find_element(By.XPATH, '//*[@id="cmbCurso"]')
    curso_elemento.click()
    curso_elemento.find_element(By.XPATH, "//option[text()='EI-EDUCAÃ‡ÃƒO INFANTIL']").click()

    periodo_elemento = driver.find_element(By.XPATH, '//*[@id="cmbPeriodo"]')
    periodo_elemento.click()
    periodo_elemento.find_element(By.XPATH, "//option[text()='AGRUPAMENTO IV']").click()

    disciplina_elemento = driver.find_element(By.XPATH, '//*[@id="cmbDisciplina"]')
    disciplina_elemento.click()
    disciplina_elemento.find_element(By.XPATH, "//option[text()='2Âº MOMENTO']").click()

    situacao_elemento = driver.find_element(By.XPATH, '//*[@id="cmbSituacaoPromocao"]')
    situacao_elemento.click()
    situacao_elemento.find_element(By.XPATH, "//option[text()='Aprovado']").click()

    FuncoesDoPrograma.marcar_checkbox(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input')
    FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtMedia"]', '0')
    
    FuncoesDoPrograma.incluir_enviar_dados(driver)

class SerieEscolhida:
    @staticmethod
    def agrupamento4(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, cursando="nao", txt_observacoes_gerais=""):
        print("executada logica para agrupamento 4")
        FuncoesDoPrograma.seleciona_terceira_janela(driver) or print('terceira janela selecionada')
        driver = FuncoesDoPrograma.preparar_formulario_inclusao(driver, ano)
        print('formulario inicial preparado')
        seletor.curso_EI_EDUCACAO_INFANTIL() or print('educacao infantil selecionado')
        seletor.periodo_EI_EDUCACAO_INFANTIL(4) or print('agrupamento 4 selecionado')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtEscola"]', nome_escola) or print('nome da escola escrito')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCidade"]', cidade) or print('nome da cidade escrito') # Escreve o valor da variÃ¡vel 'cidade' na caixa de texto '//*[@id="txtCidade"]'
        FuncoesDoPrograma.seleciona_uf() or print('uf escrito')
        escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, txt_observacoes_gerais) or print('observaÃ§Ãµes escritas')
        seletor_materia = SelecionaMateria(driver) 
        seletor_materia.momento_EI_EDUCACAO_INFANTIL("1Âº MOMENTO") or print('1Âº MOMENTO selecionado')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCHTotal"]', carga_horaria) or print('carga horaria escrita') # Escreve o valor da variÃ¡vel 'carga horaria' na caixa de texto ''//*[@id="txtCHTotal"]'
        FuncoesDoPrograma.situacao_aprovado(driver, ano, cursando) or print('SituaÃ§Ã£o selecionada com base no ano.')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtMedia"]', '0') or print('campo (obrigatorio) de media escrito 0')
        FuncoesDoPrograma.marcar_checkbox_omitir_media(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input') or print('checkbox omitir media marcado')
        FuncoesDoPrograma.clicar_botao_incluir_final(driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('janela de alerta fechada')
        seletor.curso_EI_EDUCACAO_INFANTIL() or print('educacao infantil selecionado')
        seletor.periodo_EI_EDUCACAO_INFANTIL(4) or print('agrupamento 4 selecionado')
        seletor_materia.momento_EI_EDUCACAO_INFANTIL("2Âº MOMENTO") or print('2Âº MOMENTO selecionado')
        FuncoesDoPrograma.situacao_aprovado(driver, ano, cursando) or print('SituaÃ§Ã£o selecionada com base no ano.')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtMedia"]', '0') or print('campo (obrigatorio) de media escrito 0')
        FuncoesDoPrograma.marcar_checkbox_omitir_media(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input') or print('checkbox omitir media marcado - 2Âº momento')
        FuncoesDoPrograma.clicar_botao_incluir_final(driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('janela de alerta fechada')
        FuncoesDoPrograma.clicar_item_gerado(driver, '//*[@id="panel-1"]/div[2]/div/div/table/tbody/tr[1]/td[3]') or print('1Âº momento clicado para marcar ckeckbox')
        FuncoesDoPrograma.marcar_checkbox_omitir_media(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input') or print('checkbox omitir media marcado - 1Âº momento')
        FuncoesDoPrograma.clicar_botao_incluir_final(driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('janela de alerta fechada')
        
    @staticmethod
    def agrupamento5(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, cursando="nao", txt_observacoes_gerais=""):
        print("executada logica para agrupamento 5")
        FuncoesDoPrograma.seleciona_terceira_janela(driver) or print('terceira janela selecionada')
        driver = FuncoesDoPrograma.preparar_formulario_inclusao(driver, ano)
        print('formulario inicial preparado')
        seletor.curso_EI_EDUCACAO_INFANTIL() or print('educacao infantil selecionado')
        seletor.periodo_EI_EDUCACAO_INFANTIL(5) or print('agrupamento 5 selecionado')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtEscola"]', nome_escola) or print('nome da escola escrito')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCidade"]', cidade) or print('nome da cidade escrito') # Escreve o valor da variÃ¡vel 'cidade' na caixa de texto '//*[@id="txtCidade"]'
        FuncoesDoPrograma.seleciona_uf() or print('uf escrito')
        escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, txt_observacoes_gerais) or print('observaÃ§Ãµes escritas')
        seletor_materia = SelecionaMateria(driver) 
        seletor_materia.momento_EI_EDUCACAO_INFANTIL("1Âº MOMENTO") or print('1Âº MOMENTO selecionado')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCHTotal"]', carga_horaria) or print('carga horaria escrita') # Escreve o valor da variÃ¡vel 'carga horaria' na caixa de texto ''//*[@id="txtCHTotal"]'
        FuncoesDoPrograma.situacao_aprovado(driver, ano, cursando) or print('SituaÃ§Ã£o selecionada com base no ano.')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtMedia"]', '0') or print('campo (obrigatorio) de media escrito 0')
        FuncoesDoPrograma.marcar_checkbox_omitir_media(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input') or print('checkbox omitir media marcado')
        FuncoesDoPrograma.clicar_botao_incluir_final(driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('janela de alerta fechada')
        seletor.curso_EI_EDUCACAO_INFANTIL() or print('educacao infantil selecionado')
        seletor.periodo_EI_EDUCACAO_INFANTIL(5) or print('agrupamento 5 selecionado')
        seletor_materia.momento_EI_EDUCACAO_INFANTIL("2Âº MOMENTO") or print('2Âº MOMENTO selecionado')
        FuncoesDoPrograma.situacao_aprovado(driver, ano, cursando) or print('SituaÃ§Ã£o selecionada com base no ano.')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtMedia"]', '0') or print('campo (obrigatorio) de media escrito 0')
        FuncoesDoPrograma.marcar_checkbox_omitir_media(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input') or print('checkbox omitir media marcado - 2Âº momento')
        FuncoesDoPrograma.clicar_botao_incluir_final(driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('janela de alerta fechada')
        FuncoesDoPrograma.clicar_item_gerado(driver, '//*[@id="panel-1"]/div[2]/div/div/table/tbody/tr/td[1]') or print('ARTE clicado para marcar ckeckbox')
        FuncoesDoPrograma.marcar_checkbox_omitir_media(driver, '//*[@id="card_dados_familiares"]/div[2]/div/div[2]/div[4]/div/input') or print('checkbox omitir media marcado - 1Âº momento')
        FuncoesDoPrograma.clicar_botao_incluir_final(driver, '//*[@id="panel-8"]/div[2]/div/div[3]/div[3]/button[1]') or print('botao incluir final clicado')
        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('janela de alerta fechada')

    @staticmethod
    def ano1(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados):
        print("executada logica para 1 ANO")
        FuncoesDoPrograma.seleciona_terceira_janela(driver) or print('terceira janela selecionada')
        driver = FuncoesDoPrograma.preparar_formulario_inclusao(driver, ano)
        print('formulario inicial preparado')
        seletor.curso_EF_ENSINO_FUNDAMENTAL() or print('Ensino Fundamental selecionado')
        seletor.periodo_EF_ENSINO_FUNDAMENTAL(1) or print('1Âº ano selecionado')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtEscola"]', nome_escola) or print('nome da escola escrito')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCidade"]', cidade) or print('nome da cidade escrito') # Escreve o valor da variÃ¡vel 'cidade' na caixa de texto '//*[@id="txtCidade"]'
        FuncoesDoPrograma.seleciona_uf() or print('uf escrito')
        escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados.get("txt_observacoes_gerais", "")) or print('observaÃ§Ãµes escritas')
        
        # Instanciando a classe SelecionaMateria
        seletor_materia = SelecionaMateria(driver)
        
        # Processamento das disciplinas usando os dados coletados
        processar_disciplinas_ou_registro_minimo(seletor_materia, dados, ano, carga_horaria)

        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('janela de alerta fechada')

    @staticmethod
    def ano2(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados):
        print("Executada lÃ³gica para 2Âº ANO")
        
        # Seleciona a terceira janela aberta
        FuncoesDoPrograma.seleciona_terceira_janela(driver) or print('Terceira janela selecionada')
        driver = FuncoesDoPrograma.preparar_formulario_inclusao(driver, ano)
        print('Formulario inicial preparado')
        
        # Seleciona o curso e o perÃ­odo para o 2Âº ano
        seletor.curso_EF_ENSINO_FUNDAMENTAL() or print('Ensino Fundamental selecionado')
        seletor.periodo_EF_ENSINO_FUNDAMENTAL(2) or print('2Âº ano selecionado')
        
        # Preenche informaÃ§Ãµes da escola, cidade e UF
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtEscola"]', nome_escola) or print('Nome da escola escrito')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCidade"]', cidade) or print('Nome da cidade escrito')
        FuncoesDoPrograma.seleciona_uf() or print('UF selecionada')
        
        # Escreve as observaÃ§Ãµes
        escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados.get("txt_observacoes_gerais", "")) or print('ObservaÃ§Ãµes escritas')
        
        # Instancia a classe SelecionaMateria para processar as disciplinas
        seletor_materia = SelecionaMateria(driver)
        
        # Processamento das disciplinas usando os dados coletados
        processar_disciplinas_ou_registro_minimo(seletor_materia, dados, ano, carga_horaria)

        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('Janela de alerta fechada')

    @staticmethod
    def ano3(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados):
        print("Executada lÃ³gica para 3Âº ANO")
        
        # Seleciona a terceira janela aberta
        FuncoesDoPrograma.seleciona_terceira_janela(driver) or print('Terceira janela selecionada')
        driver = FuncoesDoPrograma.preparar_formulario_inclusao(driver, ano)
        print('Formulario inicial preparado')
        
        # Seleciona o curso e o perÃ­odo para o 3Âº ano
        seletor.curso_EF_ENSINO_FUNDAMENTAL() or print('Ensino Fundamental selecionado')
        seletor.periodo_EF_ENSINO_FUNDAMENTAL(3) or print('3Âº ano selecionado')
        
        # Preenche informaÃ§Ãµes da escola, cidade e UF
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtEscola"]', nome_escola) or print('Nome da escola escrito')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCidade"]', cidade) or print('Nome da cidade escrito')
        FuncoesDoPrograma.seleciona_uf() or print('UF selecionada')
        
        # Escreve as observaÃ§Ãµes
        escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados.get("txt_observacoes_gerais", "")) or print('ObservaÃ§Ãµes escritas')
        
        # Instancia a classe SelecionaMateria para processar as disciplinas
        seletor_materia = SelecionaMateria(driver)
        
        # Processamento das disciplinas usando os dados coletados
        processar_disciplinas_ou_registro_minimo(seletor_materia, dados, ano, carga_horaria)

        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('Janela de alerta fechada')

    @staticmethod
    def ano4(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados):
        print("Executada lÃ³gica para 4Âº ANO")
        
        # Seleciona a terceira janela aberta
        FuncoesDoPrograma.seleciona_terceira_janela(driver) or print('Terceira janela selecionada')
        driver = FuncoesDoPrograma.preparar_formulario_inclusao(driver, ano)
        print('Formulario inicial preparado')
        
        # Seleciona o curso e o perÃ­odo para o 4Âº ano
        seletor.curso_EF_ENSINO_FUNDAMENTAL() or print('Ensino Fundamental selecionado')
        seletor.periodo_EF_ENSINO_FUNDAMENTAL(4) or print('4Âº ano selecionado')
        
        # Preenche informaÃ§Ãµes da escola, cidade e UF
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtEscola"]', nome_escola) or print('Nome da escola escrito')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCidade"]', cidade) or print('Nome da cidade escrito')
        FuncoesDoPrograma.seleciona_uf() or print('UF selecionada')
        
        # Escreve as observaÃ§Ãµes
        escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados.get("txt_observacoes_gerais", "")) or print('ObservaÃ§Ãµes escritas')
        
        # Instancia a classe SelecionaMateria para processar as disciplinas
        seletor_materia = SelecionaMateria(driver)
        
        # Processamento das disciplinas usando os dados coletados
        processar_disciplinas_ou_registro_minimo(seletor_materia, dados, ano, carga_horaria)

        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('Janela de alerta fechada')

    @staticmethod
    def ano5(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados):
        print("Executada lÃ³gica para 5Âº ANO")
        
        # Seleciona a terceira janela aberta
        FuncoesDoPrograma.seleciona_terceira_janela(driver) or print('Terceira janela selecionada')
        driver = FuncoesDoPrograma.preparar_formulario_inclusao(driver, ano)
        print('Formulario inicial preparado')
        
        # Seleciona o curso e o perÃ­odo para o 5Âº ano
        seletor.curso_EF_ENSINO_FUNDAMENTAL() or print('Ensino Fundamental selecionado')
        seletor.periodo_EF_ENSINO_FUNDAMENTAL(5) or print('5Âº ano selecionado')
        
        # Preenche informaÃ§Ãµes da escola, cidade e UF
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtEscola"]', nome_escola) or print('Nome da escola escrito')
        FuncoesDoPrograma.escrever_texto(driver, '//*[@id="txtCidade"]', cidade) or print('Nome da cidade escrito')
        FuncoesDoPrograma.seleciona_uf() or print('UF selecionada')
        
        # Escreve as observaÃ§Ãµes
        escrever_observacoes(driver, ano, nome_escola, cidade, ja_estudou, ficha_descritiva, txt_observacoes, serie, carga_horaria, dados.get("txt_observacoes_gerais", "")) or print('ObservaÃ§Ãµes escritas')
        
        # Instancia a classe SelecionaMateria para processar as disciplinas
        seletor_materia = SelecionaMateria(driver)
        
        # Processamento das disciplinas usando os dados coletados
        processar_disciplinas_ou_registro_minimo(seletor_materia, dados, ano, carga_horaria)

        FuncoesDoPrograma.fechar_elementos_e_alertas(driver) or print('Janela de alerta fechada')

# CÃ“DIGO
if __name__ == "__main__":
    try:
        if whatsapp_posicao.solicitar_posicao(os.path.dirname(os.path.abspath(__file__))) is None:
            sys.exit(0)
        obter_matricula()
    except Exception:
        traceback.print_exc()
        raise
    finally:
        try:
            FuncoesDoPrograma.finalizar_navegador()
        except Exception:
            traceback.print_exc()
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Tempo total de execucao: {formatar_duracao(elapsed_time)}")



'''202502171318

AlteraÃ§Ãµes realizadas:
1. "HistÃ³rico rigorosamente transcrito conforme o original" para "HistÃ³rico transcrito conforme o original"
    



'''




