from qy.evaluator import evaluate
from qy.evaluator import evaluate_source
from qy.reader import Symbol

S = Symbol


def test_arithmetic_from_qy_source():
    assert evaluate_source("(+ 1 2 3)") == 6
    assert evaluate_source("(- 10 3 2)") == 5
    assert evaluate_source("(* 2 3 4)") == 24
    assert evaluate_source("(/ 20 2 5)") == 2


def test_arithmetic_from_python_tuple_requires_symbol_operator():
    assert evaluate((S("+"), 1, 2, 3)) == 6


def test_arithmetic_from_python_tuple_rejects_string_operator():
    import pytest

    from qy.evaluator import EvaluationError

    with pytest.raises(EvaluationError):
        evaluate(("+", 1, 2))
