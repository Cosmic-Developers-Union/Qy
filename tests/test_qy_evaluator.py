import asyncio
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from qy.evaluator import ComponentDefinition
from qy.evaluator import ControlOperator
from qy.evaluator import EffectOperator
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.evaluator import ScopeOperator
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

        for name in [
            "+",
            "-",
            "*",
            "/",
            "atom",
            "eq",
            "car",
            "cdr",
            "cons",
            "str-upper",
        ]:
            self.assertIsInstance(env.resolve(S(name)), PureOperator)
        for name in ["let", "lambda", "defun", "component", "module", "from"]:
            self.assertIsInstance(env.resolve(S(name)), ScopeOperator)
        for name in ["cond"]:
            self.assertIsInstance(env.resolve(S(name)), ControlOperator)
        for name in ["print", "echo", "parallel", "cache", "spawn", "await"]:
            self.assertIsInstance(env.resolve(S(name)), EffectOperator)
        for name in ["quote"]:
            self.assertIsInstance(env.resolve(S(name)), MetaOperator)

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

    def test_lambda_creates_anonymous_function(self):
        self.assertEqual(evaluate_source("((lambda (x) (+ x 1)) 41)"), 42)
        self.assertEqual(evaluate_source("(let ((inc (lambda (x) (+ x 1)))) (inc 41))"), 42)

    def test_defun_scope_operator(self):
        env = standard_environment()
        function = evaluate_source("(defun square (x) (* x x))", env)

        self.assertIsInstance(function, UserFunction)
        self.assertEqual(evaluate_source("(square 12)", env), 144)

    def test_defun_supports_multiple_body_forms(self):
        env = standard_environment()
        evaluate_source("(defun second (x y) x y)", env)

        self.assertEqual(evaluate_source("(second 1 2)", env), 2)

    def test_component_defines_callable_component(self):
        env = standard_environment()
        component = evaluate_source("(component scale (x factor) (* x factor))", env)

        self.assertIsInstance(component, ComponentDefinition)
        self.assertEqual(evaluate_source("(scale 7 6)", env), 42)

    def test_module_defines_and_registers_exports(self):
        env = standard_environment()
        evaluate_source(
            """
            (module test.local
              (defun triple (x) (* x 3))
              (component scale (x factor) (* x factor))
              (exports triple scale))
            """,
            env,
        )
        evaluate_source("(from test.local import triple as t scale)", env)

        self.assertEqual(evaluate_source("(t 14)", env), 42)
        self.assertEqual(evaluate_source("(scale 7 6)", env), 42)

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

        @qy.register_control("unless")
        def unless(args, env):
            condition, result = args
            if evaluate(condition, env):
                return None
            return evaluate(result, env)

        @qy.register_meta("first-symbol")
        def first_symbol(expression, env):
            del env
            return expression[0]

        self.assertEqual(qy.evaluate_source("(double 21)"), 42)
        self.assertEqual(qy.evaluate_source("(unless false 7)"), 7)
        self.assertEqual(qy.evaluate_source("(first-symbol unknown)"), S("first-symbol"))

    def test_legacy_operator_registration_names_still_work(self):
        qy = Qy()

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

        self.assertIsInstance(qy.env.resolve(S("unless")), ControlOperator)
        self.assertIsInstance(qy.env.resolve(S("first-symbol")), MetaOperator)
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

    def test_from_import_supports_qy_files(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "math_ops.qy"
            path.write_text(
                """
                (defun triple (x) (* x 3))
                (component scale (x factor) (* x factor))
                """,
                encoding="utf-8",
            )
            env = standard_environment()
            evaluate_source(f'(from "{path}" import triple as t scale)', env)

            self.assertEqual(evaluate_source("(t 14)", env), 42)
            self.assertEqual(evaluate_source("(scale 7 6)", env), 42)

    def test_from_import_supports_python_files(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "math_ops.py"
            path.write_text(
                """
def triple(value):
    return value * 3

def plus_one(value):
    return value + 1
""",
                encoding="utf-8",
            )
            env = standard_environment()
            evaluate_source(f'(from "{path}" import triple as t plus-one)', env)

            self.assertEqual(evaluate_source("(t 14)", env), 42)
            self.assertEqual(evaluate_source("(plus-one 41)", env), 42)


class TestQyAsyncEvaluator(unittest.IsolatedAsyncioTestCase):
    async def test_async_api_awaits_python_coroutines(self):
        qy = Qy()

        @qy.register_pure("delayed-double")
        async def delayed_double(value):
            await asyncio.sleep(0)
            return value * 2

        self.assertEqual(await qy.evaluate_source_async("(delayed-double 21)"), 42)

    async def test_parallel_evaluates_expressions_concurrently(self):
        qy = Qy()

        @qy.register_pure("delayed")
        async def delayed(value):
            await asyncio.sleep(0)
            return value

        self.assertEqual(
            await qy.evaluate_source_async("(parallel (delayed 1) (delayed 2))"), (1, 2)
        )

    async def test_spawn_and_await_use_asyncio_tasks(self):
        qy = Qy()

        task = cast(asyncio.Task[object], await qy.evaluate_source_async("(spawn (+ 1 2))"))

        self.assertIsInstance(task, asyncio.Task)
        self.assertEqual(await task, 3)
        self.assertEqual(await qy.evaluate_source_async("(await (spawn (+ 20 22)))"), 42)

    async def test_cache_reuses_expression_result(self):
        qy = Qy()
        calls: list[int] = []

        @qy.register_pure("counted")
        def counted(value):
            calls.append(value)
            return value * 2

        self.assertEqual(await qy.evaluate_source_async("(cache (counted 21))"), 42)
        self.assertEqual(await qy.evaluate_source_async("(cache (counted 21))"), 42)
        self.assertEqual(calls, [21])


if __name__ == "__main__":
    unittest.main()
