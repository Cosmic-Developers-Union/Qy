import unittest
from pathlib import Path

from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import evaluate
from qy.evaluator import evaluate_file
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.reader import Symbol

S = Symbol


class TestQyEvaluator(unittest.TestCase):
    def test_arithmetic_from_qy_source(self):
        self.assertEqual(evaluate_source("(+ 1 2 3)"), 6)
        self.assertEqual(evaluate_source("(- 10 3 2)"), 5)
        self.assertEqual(evaluate_source("(* 2 3 4)"), 24)
        self.assertEqual(evaluate_source("(/ 20 2 5)"), 2)

    def test_arithmetic_from_python_tuple_requires_symbol_operator(self):
        self.assertEqual(evaluate((S("+"), 1, 2, 3)), 6)

        with self.assertRaises(EvaluationError):
            evaluate(("+", 1, 2))

    def test_python_tuple_atoms_are_literals_unless_symbol(self):
        self.assertEqual(evaluate("1"), "1")
        self.assertEqual(evaluate(1), 1)
        self.assertEqual(evaluate(S("1")), 1)

    def test_environment_binding_overrides_builtin_literal(self):
        env = Environment({S("1"): 10}, standard_environment())
        self.assertEqual(evaluate((S("+"), S("1"), S("2")), env), 12)

    def test_example_code001(self):
        path = Path("examples/codes/code001.qy")
        self.assertEqual(evaluate_file(path), -4162)


if __name__ == "__main__":
    unittest.main()
