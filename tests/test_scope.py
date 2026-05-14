import pytest

from qy.evaluator import EvaluationError
from qy.evaluator import evaluate
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.ir_vm import IRFunction
from qy.reader import Symbol

S = Symbol


def test_let_introduces_scope():
    assert evaluate_source("(let ((x 10) (y 20)) (+ x y))") == 30

    env = standard_environment()
    assert evaluate_source("(let ((x 10)) x)", env) == 10
    with pytest.raises(EvaluationError):
        evaluate(S("x"), env)


def test_let_can_override_literals_locally():
    assert evaluate_source("(let ((1 10)) (+ 1 2))") == 12


def test_lambda_creates_anonymous_function():
    assert evaluate_source("((lambda (x) (+ x 1)) 41)") == 42
    assert evaluate_source("(let ((inc (lambda (x) (+ x 1)))) (inc 41))") == 42


def test_defun_scope_operator():
    env = standard_environment()
    function = evaluate_source("(defun square (x) (* x x))", env)

    assert isinstance(function, IRFunction)
    assert evaluate_source("(square 12)", env) == 144


def test_defun_supports_multiple_body_forms():
    env = standard_environment()
    evaluate_source("(defun second (x y) x y)", env)

    assert evaluate_source("(second 1 2)", env) == 2


def test_self_tail_recursive_function_uses_trampoline():
    assert (
        evaluate_source(
            """
            (let ()
              (defun sum-to (n acc)
                (cond
                  ((eq n 0) acc)
                  (true (sum-to (- n 1) (+ acc n)))))
              (sum-to 300 0))
            """
        )
        == 45150
    )


def test_component_defines_callable_component():
    from qy.stdlib import load_module

    env = standard_environment()
    for sym, val in load_module("qy.legacy").exports.items():
        env.define(sym, val)
    component = evaluate_source("(component scale (x factor) (* x factor))", env)

    assert isinstance(component, IRFunction)
    assert component.kind == "function"
    assert evaluate_source("(scale 7 6)", env) == 42


def test_define_operator_binds_in_env():
    from qy import Qy

    q = Qy()
    result = q.evaluate_ir_source("(define x 42)")
    assert result == 42
    assert q.evaluate_ir_source("(+ x 1)") == 43


def test_duplicate_define_reports_error_at_lowering():
    from qy.lowering import lower_source

    result = lower_source("(define x 1) (define x 2)")
    assert any("'x' is already bound" in d.message for d in result.diagnostics)


def test_define_cannot_override_host_symbol():
    from qy.lowering import lower_source

    result = lower_source("(define + 99)")
    assert any("'+' is already bound" in d.message for d in result.diagnostics)


def test_let_can_shadow_defined_symbol():
    from qy import Qy

    q = Qy()
    q.evaluate_ir_source("(define x 1)")
    result = q.evaluate_ir_source("(let ((x 99)) x)")
    assert result == 99
    assert q.evaluate_ir_source("x") == 1


def test_define_once_raises_on_duplicate():
    from qy.environment import Environment
    from qy.errors import QyRuntimeError
    from qy.reader import Symbol

    env = Environment()
    env.define_once(Symbol("x"), 1)
    with pytest.raises(QyRuntimeError):
        env.define_once(Symbol("x"), 2)


def test_duplicate_defeffect_reports_error():
    from qy.lowering import lower_source

    result = lower_source("(defeffect ask) (defeffect ask)")
    assert any("'ask' is already bound" in d.message for d in result.diagnostics)
