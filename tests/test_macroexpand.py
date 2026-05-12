import pytest

from qy.errors import EvaluationError
from qy.evaluator import standard_environment
from qy.macroexpand import MacroExpansionOptions
from qy.macroexpand import macroexpand_source
from qy.reader import Symbol


def test_macroexpand_expands_bound_macro_call():
    env = standard_environment()
    macroexpand_source("(macro const-answer (ignored) '(+ 20 22))", env)

    expansion = macroexpand_source("(const-answer missing)", env)

    assert expansion.ok
    assert expansion.forms == [(Symbol("+"), Symbol("20"), Symbol("22"))]
    assert len(expansion.traces) == 1
    assert expansion.traces[0].macro == Symbol("const-answer")
    assert expansion.traces[0].depth == 1
    assert expansion.source_map[0].macro == Symbol("const-answer")


def test_macroexpand_keeps_quote_boundary():
    expansion = macroexpand_source("'(const-answer missing)")

    assert expansion.ok
    assert expansion.forms == [(Symbol("quote"), (Symbol("const-answer"), Symbol("missing")))]


def test_macroexpand_keeps_local_macro_scope_inside_body():
    env = standard_environment()

    expansion = macroexpand_source(
        """
        (let ()
          (macro local-answer () '(+ 1 2))
          (local-answer))
        (local-answer)
        """,
        env,
    )

    assert expansion.ok
    let_form = expansion.forms[0]
    assert isinstance(let_form, tuple)
    assert let_form[3] == (Symbol("+"), Symbol("1"), Symbol("2"))
    assert expansion.forms[1] == (Symbol("local-answer"),)
    with pytest.raises(EvaluationError):
        env.resolve(Symbol("local-answer"))


def test_macroexpand_gensym_records_generated_symbols():
    env = standard_environment()
    macroexpand_source("(macro fresh () (gensym 'tmp))", env)

    expansion = macroexpand_source("(fresh)", env)

    assert expansion.ok
    assert isinstance(expansion.forms[0], Symbol)
    assert expansion.forms[0].name.startswith("__qy_gensym_tmp_")
    assert expansion.traces[0].generated_symbols == (expansion.forms[0],)
    assert expansion.source_map[0].generated_symbols == (expansion.forms[0],)


def test_macroexpand_records_nested_trace_and_source_map_order():
    env = standard_environment()
    macroexpand_source(
        """
        (macro inner (form) (cons '+ (cons form (cons 1 '()))))
        (macro outer (form) (cons 'inner (cons form '())))
        """,
        env,
    )

    expansion = macroexpand_source("(outer 41)", env)

    assert expansion.ok
    assert expansion.forms == [(Symbol("+"), Symbol("41"), 1)]
    assert [trace.macro for trace in expansion.traces] == [Symbol("outer"), Symbol("inner")]
    assert [trace.depth for trace in expansion.traces] == [1, 2]
    assert [entry.macro for entry in expansion.source_map] == [Symbol("outer"), Symbol("inner")]
    assert [entry.depth for entry in expansion.source_map] == [1, 2]


def test_macroexpand_denies_compile_time_effects_by_default():
    env = standard_environment()
    macroexpand_source('(macro bad () (assert false "bad"))', env)

    expansion = macroexpand_source("(bad)", env)

    assert not expansion.ok
    assert "compile-time effect" in expansion.diagnostics[0].message


def test_macroexpand_reports_depth_limit_from_options():
    env = standard_environment()
    macroexpand_source("(macro self () '(self))", env)

    expansion = macroexpand_source("(self)", env, options=MacroExpansionOptions(max_depth=2))

    assert not expansion.ok
    assert "exceeded 2 nested expansions" in expansion.diagnostics[0].message
