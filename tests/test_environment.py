import pytest

from qy.errors import QyResolveError
from qy.errors import format_qy_error
from qy.evaluator import Environment
from qy.evaluator import evaluate
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.reader import Symbol

S = Symbol


def test_python_tuple_atoms_are_literals_unless_symbol():
    assert evaluate("1") == "1"
    assert evaluate(1) == 1
    assert evaluate(S("1")) == 1


def test_environment_binding_overrides_builtin_literal():
    env = Environment({S("1"): 10}, standard_environment())
    assert evaluate((S("+"), S("1"), S("2")), env) == 12


def test_unresolved_symbol_errors_include_code_span_and_qy_stack():
    with pytest.raises(QyResolveError) as exc_info:
        evaluate_source("(+ missing 1)")

    error = exc_info.value
    assert error.code == "QY_UNBOUND_SYMBOL"
    assert error.span is not None
    assert error.span.line == 1
    assert error.span.column == 4
    assert error.frames
    assert "Qy stack:" in format_qy_error(error)
