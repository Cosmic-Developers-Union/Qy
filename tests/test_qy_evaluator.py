import asyncio
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from qy.errors import QyAggregateError
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
from qy.errors import QyPythonError
from qy.errors import QyResolveError
from qy.errors import format_qy_error
from qy.evaluator import ComponentDefinition
from qy.evaluator import ControlOperator
from qy.evaluator import EffectDefinition
from qy.evaluator import EffectOperator
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import HostObjectRef
from qy.evaluator import MacroDefinition
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
from qy.values import QY_EMPTY_LIST
from qy.values import QyChain
from qy.values import list_to_qy_cons

S = Symbol


class TestQyEvaluator(unittest.TestCase):
    def test_operator_kinds(self):
        env = standard_environment()

        for name in [
            "+",
            "-",
            "*",
            "/",
            "==",
            "atom",
            "eq",
            "is",
            "car",
            "cdr",
            "cons",
            "str-upper",
            "tuple",
            "list",
            "dict",
            "set",
            "tuple?",
            "list?",
            "dict?",
            "set?",
            "len",
            "get",
            "has?",
            "type",
        ]:
            self.assertIsInstance(env.resolve(S(name)), PureOperator)
        for name in ["let", "lambda", "defun", "component", "defeffect", "module", "from"]:
            self.assertIsInstance(env.resolve(S(name)), ScopeOperator)
        for name in ["cond", "handle"]:
            self.assertIsInstance(env.resolve(S(name)), ControlOperator)
        for name in [
            "print",
            "echo",
            "assert",
            "parallel",
            "cache",
            "spawn",
            "await",
            "perform",
            "py",
            "resume",
        ]:
            self.assertIsInstance(env.resolve(S(name)), EffectOperator)
        for name in ["quote", "eval", "macro"]:
            self.assertIsInstance(env.resolve(S(name)), MetaOperator)

        for name in ["assert-failed", "python-error"]:
            effect = env.resolve(S(name))
            self.assertIsInstance(effect, EffectDefinition)
            assert isinstance(effect, EffectDefinition)
            self.assertFalse(effect.resumable)

        for name in ["set!", "set*", "setq"]:
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
        self.assertFalse(evaluate_source("(atom '(abc . def))"))
        self.assertTrue(evaluate_source("(atom '())"))
        self.assertEqual(evaluate_source("(cond (0 'truthy))"), S("truthy"))
        self.assertTrue(evaluate_source("(eq 'abc 'abc)"))
        self.assertFalse(evaluate_source("(eq '(abc) '(abc))"))
        self.assertTrue(evaluate_source("(eq '() '())"))
        self.assertFalse(evaluate_source("(eq '() none)"))
        self.assertFalse(evaluate_source("(== '() none)"))
        self.assertTrue(evaluate_source("(eq none nil)"))
        self.assertTrue(evaluate_source("(== '(abc) '(abc))"))
        self.assertFalse(evaluate_source("(is '(abc) '(abc))"))
        self.assertTrue(evaluate_source("(is '() '())"))
        self.assertEqual(evaluate_source("(type '(abc def))"), S("chain"))
        self.assertEqual(evaluate_source("(type 'abc)"), S("symbol"))
        self.assertEqual(evaluate_source("(type none)"), S("NoneType"))
        self.assertEqual(evaluate_source("(car '(abc def))"), S("abc"))
        self.assertEqual(
            evaluate_source("(cdr '(abc def ghi))"),
            list_to_qy_cons([S("def"), S("ghi")]),
        )
        self.assertEqual(
            evaluate_source("(cons 'abc '(def ghi))"),
            list_to_qy_cons([S("abc"), S("def"), S("ghi")]),
        )
        self.assertIs(evaluate_source("'()"), QY_EMPTY_LIST)
        self.assertEqual(evaluate_source("'(abc . def)"), QyChain(S("abc"), S("def")))
        self.assertEqual(evaluate_source("(cond (false 1) (true (+ 1 2)))"), 3)

    def test_core_data_type_operators(self):
        self.assertEqual(evaluate_source('(tuple 1 "two" true)'), (1, S("two"), True))
        self.assertEqual(evaluate_source('(list 1 "two" true)'), [1, S("two"), True])
        self.assertEqual(
            evaluate_source('(dict "name" "Qy" "items" (list 1 2))'),
            {S("name"): S("Qy"), S("items"): [1, 2]},
        )
        self.assertEqual(evaluate_source('(set "qy" "core" "qy")'), {S("qy"), S("core")})
        self.assertTrue(evaluate_source("(tuple? (tuple 'a 'b))"))
        self.assertFalse(evaluate_source("(list? '(a b))"))
        self.assertTrue(evaluate_source("(list? (list 1 2))"))
        self.assertEqual(evaluate_source("(list '(a b))"), [S("a"), S("b")])
        self.assertEqual(evaluate_source("(tuple '(a b))"), (S("a"), S("b")))
        self.assertTrue(evaluate_source('(dict? (dict "name" "Qy"))'))
        self.assertEqual(
            evaluate_source("(dict '((name . Qy) (mode test)))"),
            {S("name"): S("Qy"), S("mode"): S("test")},
        )
        self.assertTrue(evaluate_source('(set? (set "qy"))'))
        self.assertEqual(evaluate_source("(set '(a b a))"), {S("a"), S("b")})
        self.assertEqual(evaluate_source("(len (list 1 2 3))"), 3)
        self.assertEqual(evaluate_source("(len '(a b c))"), 3)
        self.assertEqual(evaluate_source('(get (dict "name" "Qy") "name")'), S("Qy"))
        self.assertEqual(evaluate_source('(get (list "a" "b") 1)'), S("b"))
        self.assertEqual(evaluate_source("(get '(a b c) 1)"), S("b"))
        self.assertEqual(
            evaluate_source('(get (dict "name" "Qy") "missing" "fallback")'), S("fallback")
        )
        self.assertTrue(evaluate_source('(has? (set "core") "core")'))
        self.assertTrue(evaluate_source('(has? (list "a" "b") 1)'))

    def test_list_values_work_with_car_cdr_cons(self):
        self.assertEqual(evaluate_source('(car (list "a" "b"))'), S("a"))
        self.assertEqual(evaluate_source('(cdr (list "a" "b" "c"))'), [S("b"), S("c")])
        self.assertEqual(evaluate_source('(cons \'a (list "b" "c"))'), [S("a"), S("b"), S("c")])

    def test_eval_evaluates_symbolic_forms(self):
        self.assertEqual(evaluate_source("(eval '(+ 20 22))"), 42)
        self.assertEqual(evaluate_source("(let ((form '(+ 20 22))) (eval form))"), 42)

    def test_macro_defines_ast_transform(self):
        env = standard_environment()
        macro = evaluate_source("(macro identity-form (form) form)", env)

        self.assertIsInstance(macro, MacroDefinition)
        self.assertEqual(evaluate_source("(identity-form (+ 20 22))", env), 42)

    def test_macro_receives_unevaluated_arguments(self):
        env = standard_environment()
        evaluate_source("(macro const-answer (ignored) '(+ 20 22))", env)

        self.assertEqual(evaluate_source("(const-answer missing)", env), 42)

    def test_macro_can_construct_ast_with_cons(self):
        env = standard_environment()
        evaluate_source("(macro twice (form) (cons '+ (cons form (cons form '()))))", env)

        self.assertEqual(evaluate_source("(twice (+ 1 2))", env), 6)

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

    def test_unresolved_symbol_errors_include_code_span_and_qy_stack(self):
        with self.assertRaises(QyResolveError) as raised:
            evaluate_source("(+ missing 1)")

        error = raised.exception
        self.assertEqual(error.code, "QY_UNBOUND_SYMBOL")
        self.assertIsNotNone(error.span)
        assert error.span is not None
        self.assertEqual(error.span.line, 1)
        self.assertEqual(error.span.column, 4)
        self.assertTrue(error.frames)
        self.assertIn("Qy stack:", format_qy_error(error))

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

    def test_tagged_literal_calls_user_operator_with_quoted_symbol(self):
        env = standard_environment()
        evaluate_source('(defun t (source) (str-concat "template:" source))', env)

        self.assertEqual(evaluate_source('t"hello {name}"', env), S("template:hello {name}"))

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

    async def test_py_runs_async_python_with_keyword_bindings(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            '''
            (py
              """
return a + b
"""
              :a 20
              :b 22)
            '''
        )

        self.assertEqual(result, 42)

    async def test_py_converts_hyphenated_keywords_to_python_identifiers(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            '''
            (py
              """
return user_name.upper()
"""
              :user-name "qy")
            '''
        )

        self.assertEqual(result, S("QY"))

    async def test_py_supports_await_and_awaits_returned_coroutines(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            '''
            (py
              """
async def later():
    await asyncio.sleep(0)
    return value * 2
return later()
"""
              :value 21)
            '''
        )

        self.assertEqual(result, 42)

    async def test_py_wraps_qy_callables_as_async_python_functions(self):
        qy = Qy()
        await qy.evaluate_source_async("(defun normalize-doc (doc) (str-upper doc))")

        result = await qy.evaluate_source_async(
            '''
            (py
              """
return await normalize(doc)
"""
              :doc "qy"
              :normalize normalize-doc)
            '''
        )

        self.assertEqual(result, S("QY"))

    async def test_py_converts_quoted_symbolic_literals_to_python_values(self):
        qy = Qy()
        await qy.evaluate_source_async("(defun double (x) (* x 2))")

        result = await qy.evaluate_source_async(
            '''
            (py
              """
results = []
for v in values:
    results.append(await transform(v))
return results
"""
              :values '(1 2 3 4 5)
              :transform double)
            '''
        )

        self.assertEqual(result, [2, 4, 6, 8, 10])

    async def test_py_converts_python_values_back_to_qy_values(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            '''
            (py
              """
return ["qy", 1, None, {"name": "Qy"}]
""")
            '''
        )

        self.assertEqual(result, [S("qy"), 1, None, {S("name"): S("Qy")}])

    async def test_py_preserves_core_data_types_across_bindings(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            '''
            (py
              """
return [
    type(quoted).__name__,
    type(empty).__name__,
    list(quoted),
    isinstance(xs, list),
    isinstance(point, tuple),
    isinstance(doc, dict),
    isinstance(tags, set),
    doc["name"],
    sorted(tags),
]
"""
              :quoted '(1 2)
              :empty '()
              :xs (list 1 2 3)
              :point (tuple 10 20)
              :doc (dict "name" "Qy")
              :tags (set "core" "host"))
            '''
        )

        self.assertEqual(
            result,
            [
                S("QyChain"),
                S("QyEmptyChain"),
                [1, 2],
                True,
                True,
                True,
                True,
                S("Qy"),
                [S("core"), S("host")],
            ],
        )

    async def test_py_wraps_unknown_python_objects_as_host_refs(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            '''
            (py
              """
return object()
""")
            '''
        )

        self.assertIsInstance(result, HostObjectRef)

    async def test_py_rejects_invalid_python_parameter_names(self):
        qy = Qy()

        with self.assertRaisesRegex(EvaluationError, "valid Python identifier"):
            await qy.evaluate_source_async(
                '''
                (py
                  """
return invalid_name
"""
                  :invalid-name? 1)
                '''
            )

    async def test_py_native_python_exceptions_escape_as_unhandled_effect(self):
        qy = Qy()

        with self.assertRaises(QyEffectSignal) as raised:
            await qy.evaluate_source_async(
                '''
                (py
                  """
raise ValueError("bad")
""")
                '''
            )

        error = raised.exception
        self.assertEqual(error.effect, "python-error")
        self.assertIsInstance(error.cause, QyPythonError)
        assert isinstance(error.cause, QyPythonError)
        self.assertIsInstance(error.cause.cause, ValueError)
        formatted = format_qy_error(error, debug=True)
        self.assertIn("QY_UNHANDLED_EFFECT", formatted)
        self.assertIn("effect: python-error", formatted)
        self.assertIn("Python stack:", formatted)
        self.assertIn("ValueError: bad", formatted)

    async def test_handle_can_catch_python_error_without_resume(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            '''
            (handle
              (py
                """
raise ValueError("bad")
""")
              ((python-error (err k) 'recovered)))
            '''
        )

        self.assertEqual(result, S("recovered"))

    async def test_resume_rejects_non_resumable_python_error(self):
        qy = Qy()

        with self.assertRaisesRegex(QyEffectError, "not resumable"):
            await qy.evaluate_source_async(
                '''
                (handle
                  (py
                    """
raise ValueError("bad")
""")
                  ((python-error (err k) (resume k 'ignored))))
                '''
            )

    async def test_perform_handle_resume_resumable_effect(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            """
            (let ()
              (defeffect ask)
              (handle
                (+ 1 (perform ask 41))
                ((ask (arg k) (resume k arg)))))
            """
        )

        self.assertEqual(result, 42)

    async def test_handle_without_resume_behaves_like_catch(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            """
            (let ()
              (defeffect fail)
              (handle
                (+ 1 (perform fail 41))
                ((fail (arg k) arg))))
            """
        )

        self.assertEqual(result, 41)

    async def test_resume_continues_body_after_perform(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            """
            (let ()
              (defeffect ask)
              (handle
                (let ()
                  (perform ask 1)
                  42)
                ((ask (arg k) (resume k arg)))))
            """
        )

        self.assertEqual(result, 42)

    async def test_assert_returns_truthy_condition(self):
        qy = Qy()

        result = await qy.evaluate_source_async('(assert true "ready")')

        self.assertTrue(result)

    async def test_assert_failure_raises_non_resumable_effect(self):
        qy = Qy()

        with self.assertRaises(QyEffectSignal) as raised:
            await qy.evaluate_source_async('(assert false "missing title")')

        error = raised.exception
        self.assertEqual(error.effect, "assert-failed")
        self.assertEqual(error.arg, S("missing title"))
        self.assertFalse(error.resumable)
        self.assertIsNotNone(error.span)

    async def test_handle_can_catch_assert_failure_without_resume(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            """
            (handle
              (assert false "missing title")
              ((assert-failed (err k) 'debugged)))
            """
        )

        self.assertEqual(result, S("debugged"))

    async def test_resume_rejects_non_resumable_assert_failure(self):
        qy = Qy()

        with self.assertRaisesRegex(QyEffectError, "not resumable"):
            await qy.evaluate_source_async(
                """
                (handle
                  (assert false "missing title")
                  ((assert-failed (err k) (resume k true))))
                """
            )

    async def test_resume_continues_into_assert_condition(self):
        qy = Qy()

        result = await qy.evaluate_source_async(
            """
            (let ()
              (defeffect ask)
              (handle
                (assert (perform ask nil) "missing title")
                ((ask (arg k) (resume k true)))))
            """
        )

        self.assertTrue(result)

    async def test_parallel_raises_aggregate_error(self):
        qy = Qy()

        with self.assertRaises(QyAggregateError) as raised:
            await qy.evaluate_source_async("(parallel missing absent)")

        error = raised.exception
        self.assertEqual(error.code, "QY_AGGREGATE_ERROR")
        self.assertEqual(len(error.errors), 2)
        self.assertTrue(all(item.code == "QY_UNBOUND_SYMBOL" for item in error.errors))


if __name__ == "__main__":
    unittest.main()
