import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import EvaluationOperator
from qy.evaluator import PureOperator
from qy.evaluator import SyntaxOperator
from qy.evaluator import UserFunction
from qy.evaluator import evaluate
from qy.evaluator import evaluate_file
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.reader import Symbol
from qy.runtime import Qy
from qy.stdlib import StandardModule
from qy.stdlib import register_module

S = Symbol


class TestQyEvaluator(unittest.TestCase):
    def test_operator_kinds(self):
        env = standard_environment()

        for name in ["+", "-", "*", "/", "atom", "eq", "car", "cdr", "cons"]:
            self.assertIsInstance(env.resolve(S(name)), PureOperator)
        for name in ["quote", "cond", "print", "echo", "str-upper"]:
            self.assertIsInstance(env.resolve(S(name)), EvaluationOperator)
        for name in ["defun", "from"]:
            self.assertIsInstance(env.resolve(S(name)), SyntaxOperator)

        for name in ["set", "set!", "set*", "setq"]:
            with self.assertRaises(EvaluationError):
                env.resolve(S(name))

    def test_arithmetic_from_qy_source(self):
        self.assertEqual(evaluate_source("(+ 1 2 3)"), 6)
        self.assertEqual(evaluate_source("(- 10 3 2)"), 5)
        self.assertEqual(evaluate_source("(* 2 3 4)"), 24)
        self.assertEqual(evaluate_source("(/ 20 2 5)"), 2)

    def test_basic_operators_from_qy_source(self):
        self.assertEqual(evaluate_source("'abc"), S("abc"))
        self.assertTrue(evaluate_source("(atom 'abc)"))
        self.assertFalse(evaluate_source("(atom '(abc def))"))
        self.assertTrue(evaluate_source("(atom '())"))
        self.assertTrue(evaluate_source("(eq 'abc 'abc)"))
        self.assertFalse(evaluate_source("(eq '(abc) '(abc))"))
        self.assertTrue(evaluate_source("(eq '() '())"))
        self.assertEqual(evaluate_source("(car '(abc def))"), S("abc"))
        self.assertEqual(evaluate_source("(cdr '(abc def ghi))"), (S("def"), S("ghi")))
        self.assertEqual(evaluate_source("(cons 'abc '(def ghi))"), (S("abc"), S("def"), S("ghi")))
        self.assertEqual(evaluate_source("(cond (false 1) (true (+ 1 2)))"), 3)

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

    def test_let_introduces_scope(self):
        self.assertEqual(evaluate_source("(let ((x 10) (y 20)) (+ x y))"), 30)

        env = standard_environment()
        self.assertEqual(evaluate_source("(let ((x 10)) x)", env), 10)
        with self.assertRaises(EvaluationError):
            evaluate(S("x"), env)

    def test_let_can_override_literals_locally(self):
        self.assertEqual(evaluate_source("(let ((1 10)) (+ 1 2))"), 12)

    def test_defun_syntax_operator(self):
        env = standard_environment()
        function = evaluate_source("(defun square (x) (* x x))", env)

        self.assertIsInstance(function, UserFunction)
        self.assertEqual(evaluate_source("(square 12)", env), 144)

    def test_defun_supports_multiple_body_forms(self):
        env = standard_environment()
        evaluate_source("(defun second (x y) x y)", env)

        self.assertEqual(evaluate_source("(second 1 2)", env), 2)

    def test_from_import_as_operator(self):
        env = standard_environment()
        self.assertIsNone(evaluate_source("(from qy.str import str-upper as upper)", env))

        self.assertEqual(evaluate_source('(upper "hello")', env), S("HELLO"))

    def test_from_import_supports_multiple_imports(self):
        env = standard_environment()
        evaluate_source("(from qy.str import str-upper as upper str-lower as lower)", env)

        self.assertEqual(evaluate_source('(upper "qy")', env), S("QY"))
        self.assertEqual(evaluate_source('(lower "QY")', env), S("qy"))

    def test_from_import_respects_local_scope(self):
        env = standard_environment()

        self.assertEqual(
            evaluate_source('(let () (from qy.str import str-upper as upper) (upper "qy"))', env),
            S("QY"),
        )
        with self.assertRaises(EvaluationError):
            evaluate_source('(upper "qy")', env)

    def test_from_import_supports_registered_modules(self):
        register_module(
            StandardModule(
                "test.math",
                {S("triple"): PureOperator("triple", lambda value: value * 3)},
            )
        )
        env = standard_environment()
        evaluate_source("(from test.math import triple as t)", env)

        self.assertEqual(evaluate_source("(t 14)", env), 42)

    def test_print_and_echo_return_last_value_without_rebinding(self):
        env = standard_environment()
        output = StringIO()

        with redirect_stdout(output):
            result = evaluate_source('(print "hello" (+ 1 2))', env)
            echo_result = evaluate_source('(echo "done")', env)

        self.assertEqual(result, 3)
        self.assertEqual(echo_result, S("done"))
        self.assertEqual(output.getvalue().splitlines(), ["hello 3", "done"])
        with self.assertRaises(EvaluationError):
            evaluate(S("hello"), env)

    def test_str_operators(self):
        self.assertEqual(evaluate_source('(str "hello")'), S("hello"))
        self.assertEqual(evaluate_source('(str-upper "hello")'), S("HELLO"))
        self.assertEqual(evaluate_source('(str-lower "HELLO")'), S("hello"))
        self.assertEqual(evaluate_source('(str-concat "qy" "lang")'), S("qylang"))
        self.assertEqual(evaluate_source('(str-len "hello")'), 5)
        self.assertEqual(evaluate_source('(str-split "a,b,c" ",")'), (S("a"), S("b"), S("c")))
        self.assertEqual(evaluate_source('(str-join "," \'(a b c))'), S("a,b,c"))
        self.assertEqual(evaluate_source('(str-replace "hello" "l" "x")'), S("hexxo"))
        self.assertTrue(evaluate_source('(str-contains? "hello" "ell")'))
        self.assertTrue(evaluate_source('(str-starts-with? "hello" "he")'))
        self.assertTrue(evaluate_source('(str-ends-with? "hello" "lo")'))

    def test_qy_instance_registers_external_operators(self):
        qy = Qy()

        @qy.register_pure("double")
        def double(value):
            return value * 2

        @qy.register_evaluation("unless")
        def unless(args, env):
            condition, result = args
            if evaluate(condition, env):
                return None
            return evaluate(result, env)

        @qy.register_syntax("first-symbol")
        def first_symbol(expression, env):
            del env
            return expression[0]

        self.assertEqual(qy.evaluate_source("(double 21)"), 42)
        self.assertEqual(qy.evaluate_source("(unless false 7)"), 7)
        self.assertEqual(qy.evaluate_source("(first-symbol unknown)"), S("first-symbol"))

    def test_example_code001(self):
        path = Path("examples/codes/code001.qy")
        result = evaluate_file(path)

        assert isinstance(result, float)
        self.assertAlmostEqual(result, 51926.26973684211)

    def test_evaluate_file_runs_program_and_returns_last_value(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "program.qy"
            path.write_text(
                """
                (from qy.str import str-upper as upper)
                (upper "qy")
                """,
                encoding="utf-8",
            )

            self.assertEqual(evaluate_file(path), S("QY"))


if __name__ == "__main__":
    unittest.main()
