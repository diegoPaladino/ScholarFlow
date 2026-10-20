"""Credenciais locais protegidas pelo Windows para o usuário atual."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path

ARQUIVO = Path(__file__).resolve().with_name('gemul_credenciais.dpapi')


def _proteger(dados, descriptografar=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(dados)
    entrada = Blob(len(dados), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    saida = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    funcao = crypt.CryptUnprotectData if descriptografar else crypt.CryptProtectData
    funcao.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    funcao.restype = wintypes.BOOL
    if not funcao(ctypes.byref(entrada), None, None, None, None, 1, ctypes.byref(saida)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(saida.data, saida.size)
    finally:
        kernel.LocalFree(ctypes.cast(saida.data, ctypes.c_void_p))


def carregar():
    if not ARQUIVO.exists():
        return {}
    return json.loads(_proteger(ARQUIVO.read_bytes(), True).decode('utf-8'))


def salvar(usuario, senha):
    dados = json.dumps({'usuario': usuario, 'senha': senha}, ensure_ascii=False).encode('utf-8')
    temporario = ARQUIVO.with_suffix('.tmp')
    try:
        temporario.write_bytes(_proteger(dados))
        temporario.replace(ARQUIVO)
    finally:
        temporario.unlink(missing_ok=True)


def esquecer():
    ARQUIVO.unlink(missing_ok=True)
