from qy.frontend.reader import Symbol
from qy.runtime import evaluate
from qy.runtime import evaluate_source

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

    from qy.errors import EvaluationError

    with pytest.raises(EvaluationError):
        evaluate(("+", 1, 2))
