from qy.core.syntax import Symbol
from qy.core.syntax import list_to_chain
from qy.runtime import evaluate
from qy.runtime import evaluate_source

S = Symbol


def L(*items: object) -> object:
    """构造一个 Qy call form（chain）。."""
    return list_to_chain(list(items))


def test_arithmetic_from_qy_source():
    assert evaluate_source("(+ 1 2 3)") == 6
    assert evaluate_source("(- 10 3 2)") == 5
    assert evaluate_source("(* 2 3 4)") == 24
    assert evaluate_source("(/ 20 2 5)") == 2


def test_arithmetic_from_python_host_form_requires_symbol_operator():
    assert evaluate(L(S("+"), 1, 2, 3)) == 6


def test_arithmetic_from_python_host_form_rejects_string_operator():
    import pytest

    from qy.errors import EvaluationError

    with pytest.raises(EvaluationError):
        evaluate(L("+", 1, 2))
