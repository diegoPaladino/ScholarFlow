"""Visible operation feedback; browser automation remains on its owning thread."""
import tkinter as tk
from tkinter import ttk


class ProgressoOperacao:
    def __init__(self, parent, descricao):
        self.janela = tk.Toplevel(parent)
        self.janela.title('Andamento do lançamento')
        self.janela.attributes('-topmost', True)
        self.janela.geometry('540x245')
        self.janela.resizable(False, False)
        self.finalizado = False
        self.janela.protocol('WM_DELETE_WINDOW', self.fechar)
        quadro = ttk.Frame(self.janela, padding=18)
        quadro.pack(fill='both', expand=True)
        ttk.Label(quadro, text=descricao, wraplength=500).pack(anchor='w', pady=(0, 14))
        self.estado = tk.StringVar(value='Iniciando...')
        ttk.Label(quadro, textvariable=self.estado, wraplength=500).pack(anchor='w', fill='x')
        self.botao = ttk.Button(quadro, text='Fechar', command=self.fechar, state='disabled')
        self.botao.pack(side='bottom', anchor='e', pady=(12, 0))
        self.atualizar('Preparando o lançamento...')

    def atualizar(self, mensagem):
        self.estado.set(mensagem)
        self.janela.lift()
        self.janela.update_idletasks()

    def concluir(self, mensagem, falha=False):
        self.finalizado = True
        self.janela.title('Lançamento interrompido' if falha else 'Resultado do lançamento')
        self.botao.state(['!disabled'])
        self.atualizar(mensagem)
        self.janela.bell()
        self.janela.focus_force()

    def fechar(self):
        if self.finalizado:
            self.janela.destroy()
