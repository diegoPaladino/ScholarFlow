"""Capture a user-selected screen position for future WhatsApp features."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import messagebox


def salvar_posicao(base_dir, x, y):
    base = Path(base_dir)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=base,
                                         suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"x": int(x), "y": int(y)}, file)
            file.write("\n")
        os.replace(temporary, base / "whatsapp_posicao.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def carregar_posicao(base_dir):
    return json.loads((Path(base_dir) / "whatsapp_posicao.json").read_text(encoding="utf-8"))


def solicitar_posicao(base_dir):
    """Wait for a fresh left click, without intercepting or generating clicks."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result = []
    try:
        if not messagebox.askokcancel(
            "Posição do WhatsApp",
            "Deixe o navegador com o WhatsApp aberto.\n\n"
            "Após clicar em OK, clique uma vez exatamente no local da tela "
            "que deseja memorizar para acessar esse navegador.\n\n"
            "A posição será salva para uso posterior. Pressione Esc para cancelar.",
            parent=root,
        ):
            return None
        # Wait for the instruction dialog's click to be released first.
        released = False
        deadline = time.monotonic() + 120
        done = tk.BooleanVar(root, False)

        def poll():
            nonlocal released
            if user32.GetAsyncKeyState(0x1B) & 0x8000:
                done.set(True)
                return
            if time.monotonic() >= deadline:
                done.set(True)
                return
            pressed = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
            if not pressed:
                released = True
            elif released:
                point = wintypes.POINT()
                if not user32.GetCursorPos(ctypes.byref(point)):
                    done.set(True)
                    return
                result.append({"x": point.x, "y": point.y})
                done.set(True)
                return
            root.after(10, poll)

        root.after(10, poll)
        root.wait_variable(done)
        if not result:
            messagebox.showinfo("Posição do WhatsApp", "Captura cancelada. A execução será encerrada.", parent=root)
            return None
        position = result[0]
        try:
            salvar_posicao(base_dir, **position)
        except OSError as exc:
            messagebox.showerror("Posição do WhatsApp", f"Não foi possível salvar a posição:\n{exc}", parent=root)
            raise
        return position
    finally:
        root.destroy()
