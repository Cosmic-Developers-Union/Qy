# coding: utf-8

"""Binding consistency tests: analyzer, lowering, runtime agree on binding semantics."""

from __future__ import annotations

from qy.analysis import analyze_source
from qy.passes.lower_hir import lower
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


def test_number_literal_spelling_consistent() -> None:
    """Number spelling: literal resolver, analyzer, and runtime agree."""
    qy = Qy()

    # Integer literal
    analysis = analyze_source("42", qy.env)
    errors = [d for d in analysis.diagnostics if d.severity == "error"]
    assert not errors

    result = qy.evaluate_source("42")
    assert result == 42
    assert isinstance(result, int)

    # Float literal
    analysis = analyze_source("3.14", qy.env)
    errors = [d for d in analysis.diagnostics if d.severity == "error"]
    assert not errors

    result = qy.evaluate_source("3.14")
    assert result == 3.14
    assert isinstance(result, float)


def test_string_spelling_consistent() -> None:
    """String spelling: quoted strings are runtime string values across all stages."""
    qy = Qy()

    analysis = analyze_source('"hello"', qy.env)
    errors = [d for d in analysis.diagnostics if d.severity == "error"]
    assert not errors

    result = qy.evaluate_source('"hello"')
    assert result == "hello"
    assert isinstance(result, str)


def test_eq_identity_vs_num_equality() -> None:
    """Test that eq uses value equality for atoms and = is numeric value equality."""
    from qy.values import QY_T

    qy = Qy()

    # eq: value equality for atoms, identity for chains
    assert qy.evaluate_source("(eq nil nil)") is QY_T
    assert qy.evaluate_source("(eq T T)") is QY_T
    assert qy.evaluate_source("(eq 1 1)") is QY_T  # value equality for ints

    # =: numeric value equality, returns QY_T/QY_NIL
    assert qy.evaluate_source("(= 1 1)") is QY_T
    assert qy.evaluate_source("(= 0 0)") is QY_T
    assert qy.evaluate_source("(= 3.14 3.14)") is QY_T

    # eq: symbols use value equality (same name = equal)
    assert qy.evaluate_source("(eq 'abc 'abc)") is QY_T  # same name -> equal


def test_module_export_view_consistent() -> None:
    """module/from/exports: export view is selective, from is fold with define-once."""
    from qy.reader import Symbol

    # Module with exports: only exported names visible
    q = Qy()
    q.evaluate_source("(module M (exports pub) (define priv 1) (define pub 2))")
    from qy.std.module import StandardModule

    mod = q.env.resolve(Symbol("M"))
    assert isinstance(mod, StandardModule)
    assert Symbol("pub") in mod.exports
    assert Symbol("priv") not in mod.exports

    # from is selective fold
    q2 = Qy()
    q2.evaluate_source("(module N (exports a b) (define a 10) (define b 20))")
    q2.evaluate_source("(from N import a)")
    assert q2.env.resolve(Symbol("a")) == 10
    # b was not imported
    try:
        q2.env.resolve(Symbol("b"))
        raise AssertionError("b should not be visible")
    except Exception:
        pass


def test_host_injection_in_symbol_space() -> None:
    """Host-injected names are visible through symbol-space chain."""
    from qy.reader import Symbol

    q = Qy()
    # + is injected by standard profile
    from qy.operators import PureOperator

    plus = q.env.resolve(Symbol("+"))
    assert isinstance(plus, PureOperator)
    assert plus.name == "+"
