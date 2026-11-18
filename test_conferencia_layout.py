import ast
from datetime import datetime
import os
from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

import boletim_bimestral as boletim


class ConferenciaLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('1024x600')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.tree = ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))

    def children(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self.children(child)

    def load(self, name, env):
        node = next(n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef) and n.name == name)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<layout>', 'exec'), env)
        return env[name]

    def test_action_bar_stays_visible_as_form_grows_and_window_shrinks(self):
        form, actions = self.load('criar_area_formulario', dict(tk=tk, ttk=ttk))(self.root)
        button = ttk.Button(actions, text='OK')
        button.pack()
        label = ttk.Label(form, text='Dados\n' * 100, width=160)
        label.grid()
        self.root.deiconify()
        for width, height in ((1366, 680), (1024, 600), (900, 500)):
            with self.subTest(width=width, height=height):
                self.root.geometry(f'{width}x{height}')
                self.root.update()
                self.assertGreaterEqual(button.winfo_rooty(), self.root.winfo_rooty())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                     self.root.winfo_rooty() + self.root.winfo_height())
                canvas = form.master
                self.assertGreater(form.winfo_height(), canvas.winfo_height())
                canvas.yview_moveto(1)
                self.root.update()
                self.assertGreater(canvas.yview()[0], 0)

    def test_review_shows_terms_and_saves_only_the_corrected_cell(self):
        data = dict(numero_matricula='202600001', nome_aluno='ALUNO TESTE', ano='2026', turma='4 ANO A',
                    notas=[dict(disciplina='ARTES', bimestre='1', nota='0'),
                           dict(disciplina='ARTES', bimestre='2', nota='8.5'),
                           dict(disciplina='MATEMÁTICA', bimestre='1', nota='9')])
        state = {'resultado': data, 'arquivos': []}
        env = dict(tk=tk, ttk=ttk, root=self.root, re=re, os=os, datetime=datetime,
                   __file__=str(Path('main.py').resolve()), boletim_bimestral=boletim,
                   estado_boletim=state, numero_matricula_var=tk.StringVar(self.root, value='202600001'),
                   status_boletim_var=tk.StringVar(self.root), carregar_base_rel_aluno=lambda: [],
                   messagebox=Mock())
        self.load('revisar_boletim', env)()
        window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        self.root.update()
        widgets = list(self.children(window))
        table = next(w for w in widgets if isinstance(w, ttk.Treeview))
        self.assertEqual(tuple(table['columns']), ('disciplina', 'b1', 'b2', 'b3', 'b4'))
        rows = table.get_children()
        self.assertEqual(len(rows), 2)
        self.assertEqual(tuple(table.item(rows[0], 'values')), ('ARTES', '0', '8.5', '', ''))
        table.selection_set(rows[0])
        combo = next(w for w in widgets if isinstance(w, ttk.Combobox))
        combo.set('2')
        combo.event_generate('<<ComboboxSelected>>')
        self.root.update()
        entries = [w for w in widgets if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
        note = entries[-1]
        self.assertEqual(note.get(), '8.5')
        note.delete(0, 'end')
        note.insert(0, '7.5')
        next(w for w in widgets if isinstance(w, ttk.Button) and w['text'] == 'Aplicar correção').invoke()
        with patch.object(boletim, 'salvar', side_effect=lambda base, mat, novo, files: boletim.validar(novo, mat)) as save:
            next(w for w in widgets if isinstance(w, ttk.Button) and w['text'] == 'Salvar revisão').invoke()
            self.assertEqual(save.call_count, 1)
        notes = {(n['disciplina'], n['bimestre']): n['nota'] for n in state['resultado']['notas']}
        self.assertEqual(notes, {('ARTES', '1'): '0', ('ARTES', '2'): '7.5', ('MATEMÁTICA', '1'): '9'})

    def test_review_round_trip_preserves_blanks_and_zero(self):
        notas = [dict(disciplina='ARTES', bimestre='1', nota='0'),
                 dict(disciplina='ARTES', bimestre='4', nota='8,5')]
        self.assertEqual(boletim.notas_da_conferencia(boletim.linhas_conferencia(notas)), notas)


if __name__ == '__main__':
    unittest.main()
