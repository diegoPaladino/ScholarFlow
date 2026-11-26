import unittest
from idp_benchmark import evaluate


class BenchmarkTests(unittest.TestCase):
    def test_counts(self):
        r = evaluate({'a': '1', 'b': '2', 'c': '3'}, {'a': '1', 'b': '9', 'd': '4'})
        self.assertEqual((r['correct'], r['wrong'], r['missing'], r['extra']), (1, 1, 1, 1))
        self.assertEqual(r['union_accuracy'], .25)

    def test_zero_and_blank(self):
        self.assertEqual(evaluate({'a': '0', 'b': ''}, {'a': '', 'b': ''})['correct'], 1)

    def test_types(self):
        self.assertEqual(evaluate({'a': 1}, {'a': True})['wrong'], 1)

    def test_reordered_notes(self):
        rows = [{'disciplina': 'A', 'bimestre': '1', 'nota': '0'}, {'disciplina': 'B', 'bimestre': '2', 'nota': '9'}]
        self.assertEqual(evaluate({'notas': rows}, {'notas': rows[::-1]})['accuracy'], 1)

    def test_years_and_extras(self):
        row = {'ano': '2025', 'serie': '1', 'disciplinas_extra': [{'disciplina': 'A', 'nota': '8'}]}
        self.assertEqual(evaluate({'historicos': [row]}, {'historicos': []})['missing'], 1)

    def test_duplicate(self):
        row = {'disciplina': 'A', 'bimestre': '1', 'nota': '8'}
        with self.assertRaises(ValueError):
            evaluate({'notas': [row]}, {'notas': [row, row]})

    def test_empty(self):
        self.assertIsNone(evaluate({}, {})['accuracy'])

    def test_invalid_identity(self):
        with self.assertRaises(ValueError):
            evaluate({}, {'historicos': [{'ano': '2025'}]})

    def test_no_values_in_result(self):
        self.assertNotIn('SYNTHETIC_SECRET', str(evaluate({'nome_aluno': 'SYNTHETIC_SECRET'}, {})))
