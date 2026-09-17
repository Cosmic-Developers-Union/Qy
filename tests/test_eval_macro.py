import pytest

from qy.async_utils import run_coro
from qy.core.syntax import Symbol
from qy.errors import EvaluationError
from qy.frontend.reader import read_one
from qy.macro.evaluator import evaluate_compile_time_body
from qy.runtime import evaluate_source
from qy.session.runtime_space import create_standard_runtime_space as standard_environment

S = Symbol


def test_eval_evaluates_symbolic_forms():
    assert evaluate_source("(eval '(+ 20 22))") == 42
    assert evaluate_source("(let ((form '(+ 20 22))) (eval form))") == 42


def test_macro_defines_ast_transform():
    env = standard_environment()
    macro = evaluate_source("(macro identity-form (form) form)", env)

    assert macro is None
    with pytest.raises(EvaluationError):
        env.resolve(S("identity-form"))
    assert evaluate_source("(identity-form (+ 20 22))", env) == 42


def test_macro_receives_unevaluated_arguments():
    env = standard_environment()
    evaluate_source("(macro const-answer (ignored) '(+ 20 22))", env)

    assert evaluate_source("(const-answer missing)", env) == 42


def test_lambda_parameter_named_macro_is_not_a_macro_definition():
    """回归：参数列表 ``(macro)`` 不得被 macroexpander 当作宏定义。."""
    source = """
    (define apply-param (lambda (macro) macro))
    (apply-param 7)
    """
    assert evaluate_source(source) == 7


def test_macro_can_construct_ast_with_cons():
    env = standard_environment()
    evaluate_source("(macro twice (form) (cons '+ (cons form (cons form '()))))", env)

    assert evaluate_source("(twice (+ 1 2))", env) == 6


def test_macro_gensym_avoids_capturing_user_variable():
    env = standard_environment()
    evaluate_source(
        """
                (macro bind-temp (value)
                    (let ((tmp (gensym 'tmp)))
                        (cons 'let
                            (cons
                                (cons (cons tmp (cons value '())) '())
                                (cons tmp '())))))
                """,
        env,
    )

    assert evaluate_source("(let ((tmp 99)) (bind-temp 42))", env) == 42


def test_macro_hygiene_example_use_temp_keeps_outer_binding_intact():
    env = standard_environment()
    evaluate_source(
        """
        (macro use-temp (value)
          (cons 'let
            (cons
              (cons (cons 'tmp (cons value '())) '())
              (cons 'tmp '()))))
        """,
        env,
    )

    assert evaluate_source("(let ((tmp 99)) (use-temp 42))", env) == 42


def test_macro_hygiene_call_site_symbol_should_not_be_captured():
    env = standard_environment()
    evaluate_source(
        """
        (macro with-temp (expr)
          (cons 'let
            (cons
              (cons (cons 'tmp (cons 1 '())) '())
              (cons expr '()))))
        """,
        env,
    )

    assert evaluate_source("(let ((tmp 99)) (with-temp tmp))", env) == 99


def test_macro_hygiene_definition_site_core_binding_should_not_be_shadowed():
    env = standard_environment()
    evaluate_source(
        """
        (macro add-one (value)
          (cons '+ (cons value (cons 1 '()))))
        """,
        env,
    )

    assert (
        evaluate_source(
            """
            (let ((+ (lambda (a b) 0)))
              (add-one 41))
            """,
            env,
        )
        == 42
    )


def test_macro_capture_allows_intentional_call_site_capture():
    env = standard_environment()
    evaluate_source(
        """
        (macro call-site-plus (value)
          (cons (capture '+) (cons value (cons 1 '()))))
        """,
        env,
    )

    assert (
        evaluate_source(
            """
            (let ((+ (lambda (a b) 0)))
              (call-site-plus 41))
            """,
            env,
        )
        == 0
    )


def test_macro_hygiene_lambda_params_do_not_capture_call_site_symbols():
    env = standard_environment()
    evaluate_source(
        """
                (macro wrap-lambda (expr)
                    (cons 'lambda
                        (cons (cons 'tmp '())
                            (cons expr '()))))
                """,
        env,
    )

    assert (
        evaluate_source(
            """
                        (let ((tmp 99))
                            ((wrap-lambda tmp) 1))
                        """,
            env,
        )
        == 99
    )


def test_macro_hygiene_defun_params_do_not_capture_call_site_symbols():
    env = standard_environment()
    evaluate_source(
        """
                (macro define-using (expr)
                    (cons 'defun
                        (cons 'use-outer
                            (cons (cons 'tmp '())
                                (cons expr '())))))
                """,
        env,
    )

    assert (
        evaluate_source(
            """
                        (let ((tmp 99))
                            (define-using tmp)
                            (use-outer 1))
                        """,
            env,
        )
        == 99
    )


def test_macro_hygiene_alias_not_in_env_bindings():
    """F2: hygiene aliases must not appear in env.bindings() (REPL/debug visibility)."""
    env = standard_environment()
    evaluate_source(
        """
        (macro add-one (x)
          (cons '+ (cons x (cons 1 '()))))
        (add-one 41)
        """,
        env,
    )
    visible_names = {sym.name for sym in env.bindings()}
    assert not any(name.startswith("__qy_hygiene_") for name in visible_names), (
        f"hygiene aliases leaked into env.bindings(): {[n for n in visible_names if n.startswith('__qy_hygiene_')]}"
    )


def test_macro_hygiene_handle_params_do_not_capture_call_site_symbols():
    env = standard_environment()
    evaluate_source(
        """
                (macro handle-ask (body)
                    (cons 'handle
                        (cons
                            (cons 'perform (cons 'ask (cons 1 '())))
                            (cons
                                (cons
                                    (cons 'ask
                                        (cons
                                            (cons 'tmp (cons 'k '()))
                                            (cons body '())))
                                    '())
                                '()))))
                """,
        env,
    )

    assert (
        evaluate_source(
            """
                        (let ((tmp 99))
                            (defeffect ask)
                            (handle-ask tmp))
                        """,
            env,
        )
        == 99
    )


def test_compile_time_lambda_can_be_called_during_expansion():
    """Compile-time lambda 必须是编译期函数值，不能变成 VM 函数值。."""
    assert evaluate_source("(macro m () ((lambda (x) (+ x 1)) 41))\n(m)") == 42


def test_compile_time_defun_can_be_called_during_expansion():
    assert evaluate_source("(macro m () (defun h (x) (+ x 2)) (h 40))\n(m)") == 42


def test_compile_time_function_value_is_macro_function():
    """编译期 lambda 得到 MacroFunction（而不是运行期 VM 值）。."""
    from qy.macro import MacroFunction
    from qy.vm.bytecode import BytecodeFunctionValue

    env = standard_environment()
    value = run_coro(
        evaluate_compile_time_body(
            (read_one("(lambda (x) x)"),),
            env,
        )
    )

    assert isinstance(value, MacroFunction)
    assert not isinstance(value, BytecodeFunctionValue)


def test_compile_time_recursion_through_defun():
    source = """
    (macro m ()
      (defun f (n) (cond ((= n 0) 0) ((< 0 n) (+ n (f (- n 1))))))
      (f 5))
    (m)
    """

    assert evaluate_source(source) == 15
