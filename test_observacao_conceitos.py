import unittest

from disciplinas_historico import normalizar_observacao_conceitos


class ObservacaoConceitosTests(unittest.TestCase):
    def test_mixed_concepts_are_grouped_without_losing_math_b(self):
        source = ('Aluno(a) recebeu conceitos nas matérias: Língua Portuguesa (A); '
                  'Matemática (B); História (A); Geografia (A); Ciências (A); Arte (A); '
                  'Educação Física (A); Ensino Religioso (A). Histórico transcrito conforme o original.')
        expected = ('Aluno(a) recebeu o conceito "A" nas matérias: Língua Portuguesa; História; '
                    'Geografia; Ciências; Arte; Educação Física; Ensino Religioso. '
                    'Aluno(a) recebeu o conceito "B" na matéria: Matemática. '
                    'Histórico transcrito conforme o original.')
        self.assertEqual(normalizar_observacao_conceitos(source), expected)
        self.assertEqual(normalizar_observacao_conceitos(expected), expected)

    def test_uniform_concepts_and_other_information_are_preserved(self):
        text = ('Aluno(a) recebeu conceitos nas matérias: Português (A); Matemática (A). '
                'Transferência em agosto.')
        self.assertEqual(normalizar_observacao_conceitos(text),
                         'Aluno(a) recebeu o conceito "A" nas matérias: Português; Matemática. '
                         'Transferência em agosto.')

    def test_unknown_or_numeric_evaluations_are_not_rewritten(self):
        for text in ('Aluno(a) recebeu conceitos nas matérias: Matemática (8); Arte (A).',
                     'Aluno(a) recebeu conceitos nas matérias: Matemática (A); Arte (não informado).',
                     'Sem observações.'):
            self.assertEqual(normalizar_observacao_conceitos(text), text)


if __name__ == '__main__':
    unittest.main()
