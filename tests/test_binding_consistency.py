# coding: utf-8

"""Binding consistency tests: analyzer, lowering, runtime agree on binding semantics."""

from __future__ import annotations

from qy.analyzer import analyze_source
from qy.lowering import lower
from qy.reader import read
from qy.runtime import Qy


def test_define_resolves_consistently() -> None:
    """Define + resolve: all three stages agree."""
    qy = Qy()
    source = "(define x 42)"
    forms = read(source)

    # Analyze: no error diagnostics
    analysis = analyze_source(source, qy.env)
    errors = [d for d in analysis.diagnostics if d.severity == "error"]
    assert not errors, f"analyzer errors: {[d.message for d in errors]}"

    # Lower: no error diagnostics
    program = lower(forms, qy.env)
    errors = [d for d in program.diagnostics if d.severity == "error"]
    assert not errors, f"lowering errors: {[d.message for d in errors]}"

    # Runtime: evaluate succeeds, x is bound
    qy.evaluate_source(source)
    from qy.reader import Symbol

    assert qy.env.resolve(Symbol("x")) == 42


def test_let_scope_resolves_consistently() -> None:
    """Let child scope: analyzer and runtime agree."""
    qy = Qy()
    source = "(let ((y 10)) y)"

    analysis = analyze_source(source, qy.env)
    errors = [d for d in analysis.diagnostics if d.severity == "error"]
    assert not errors

    result = qy.evaluate_source(source)
    assert result == 10


def test_from_fold_visible_consistently() -> None:
    """From import: fold-visible in all stages (using alias to avoid define-once conflict)."""
    qy = Qy()
    source = "(from qy.num import + as my-add) (my-add 1 2)"
    forms = read(source)

    analysis = analyze_source(source, qy.env)
    errors = [d for d in analysis.diagnostics if d.severity == "error"]
    assert not errors, f"analyzer errors: {[d.message for d in errors]}"

    program = lower(forms, qy.env)
    errors = [d for d in program.diagnostics if d.severity == "error"]
    assert not errors, f"lowering errors: {[d.message for d in errors]}"

    result = qy.evaluate_source(source)
    assert result == 3


def test_define_once_error_consistent() -> None:
    """Same-scope re-define: analyzer and lowering both error."""
    qy = Qy()
    source = "(define x 1) (define x 2)"
    forms = read(source)

    # Analyze should report error
    analysis = analyze_source(source, qy.env)
    analysis_errors = [d for d in analysis.diagnostics if d.severity == "error"]
    assert analysis_errors, "analyzer should report define-once violation"

    # Lower should also report error
    program = lower(forms, qy.env)
    lowering_errors = [d for d in program.diagnostics if d.severity == "error"]
    assert lowering_errors, "lowering should report define-once violation"


def test_pre_symbol_space_chain_readable() -> None:
    """Qy instance exposes readable pre-symbol-space chain."""
    qy = Qy()
    chain = qy.pre_symbol_space_chain
    assert chain is not None
    assert isinstance(chain, tuple)
    assert len(chain) > 0
    # Each frame should have bindings
    for frame in chain:
        assert hasattr(frame, "bindings")
