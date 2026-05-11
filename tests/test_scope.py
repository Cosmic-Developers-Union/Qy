import pytest

from qy.evaluator import ComponentDefinition
from qy.evaluator import EvaluationError
from qy.evaluator import UserFunction
from qy.evaluator import evaluate
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
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

    assert isinstance(function, UserFunction)
    assert evaluate_source("(square 12)", env) == 144


def test_defun_supports_multiple_body_forms():
    env = standard_environment()
    evaluate_source("(defun second (x y) x y)", env)

    assert evaluate_source("(second 1 2)", env) == 2


def test_component_defines_callable_component():
    env = standard_environment()
    component = evaluate_source("(component scale (x factor) (* x factor))", env)

    assert isinstance(component, ComponentDefinition)
    assert evaluate_source("(scale 7 6)", env) == 42
