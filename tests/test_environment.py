import pytest

from qy.analysis import analyze_source
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import QyResolveError
from qy.errors import format_qy_error
from qy.frontend.reader import Symbol
from qy.passes.lower_hir import lower_source
from qy.runtime import evaluate
from qy.runtime import evaluate_source
from qy.sem.core import IntValue
from qy.session.pre_ss import resolve_default_literal

S = Symbol


def test_python_tuple_atoms_are_literals_unless_symbol():
    assert evaluate("1") == "1"
    assert evaluate(1) == 1
    assert evaluate(S("1")) == IntValue(1)


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


def test_environment_can_use_custom_literal_resolver():
    def resolver(symbol: Symbol) -> object:
        if symbol == S("answer"):
            return 42
        return resolve_default_literal(symbol)

    env = Environment(literal_resolver=resolver)
    assert evaluate(S("answer"), env) == 42


def test_child_environment_inherits_custom_literal_resolver():
    def resolver(symbol: Symbol) -> object:
        if symbol == S("v"):
            return 7
        return resolve_default_literal(symbol)

    env = Environment(literal_resolver=resolver)
    assert evaluate(S("v"), env.child()) == 7


def test_analyzer_and_lowering_read_same_environment_literal_facts():
    def resolver(symbol: Symbol) -> object:
        if symbol == S("forty-two"):
            return 42
        return resolve_default_literal(symbol)

    env = standard_environment(literal_resolver=resolver)

    analysis = analyze_source("(+ forty-two 1)", env)
    lowered = lower_source("(+ forty-two 1)", env)

    assert not any(item.severity == "error" for item in analysis.diagnostics)
    assert not any(item.severity == "error" for item in lowered.diagnostics)
    assert evaluate_source("(+ forty-two 1)", env) == 43
