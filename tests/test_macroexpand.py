import pytest

from qy.errors import EvaluationError
from qy.evaluator import standard_environment
from qy.macro import MacroDefinition
from qy.macroexpand import MacroExpansionOptions
from qy.macroexpand import macroexpand_source
from qy.reader import Symbol
from qy.stdlib import StandardModule
from qy.stdlib import register_module


def test_macroexpand_expands_bound_macro_call():
    env = standard_environment()
    macroexpand_source("(macro const-answer (ignored) '(+ 20 22))", env)

    with pytest.raises(EvaluationError):
        env.resolve(Symbol("const-answer"))

    expansion = macroexpand_source("(const-answer missing)", env)

    assert expansion.ok
    expanded = expansion.forms[0]
    assert isinstance(expanded, tuple)
    assert isinstance(expanded[0], Symbol)
    assert expanded[1:] == (Symbol("20"), Symbol("22"))
    assert len(expansion.traces) == 1
    assert expansion.traces[0].macro == Symbol("const-answer")
    assert expansion.traces[0].depth == 1
    assert expansion.source_map[0].macro == Symbol("const-answer")
    assert len(expansion.traces[0].renames) == 1
    assert expansion.traces[0].renames[0].original == Symbol("+")
    assert expansion.traces[0].renames[0].kind == "definition-site"
    assert expanded[0].name == expansion.traces[0].renames[0].rewritten.name
    assert expansion.source_map[0].renames == expansion.traces[0].renames


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
    inner = let_form[3]
    assert isinstance(inner, tuple)
    assert isinstance(inner[0], Symbol)
    assert inner[1:] == (Symbol("1"), Symbol("2"))
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
    expanded = expansion.forms[0]
    assert isinstance(expanded, tuple)
    assert isinstance(expanded[0], Symbol)
    assert expanded[1:] == (Symbol("41"), 1)
    assert [trace.macro for trace in expansion.traces] == [Symbol("outer"), Symbol("inner")]
    assert [trace.depth for trace in expansion.traces] == [1, 2]
    assert [entry.macro for entry in expansion.source_map] == [Symbol("outer"), Symbol("inner")]
    assert [entry.depth for entry in expansion.source_map] == [1, 2]
    assert expansion.traces[0].renames == ()
    assert len(expansion.traces[1].renames) == 1
    assert expansion.traces[1].renames[0].original == Symbol("+")


def test_macroexpand_records_binding_hygiene_renames_in_trace_and_source_map():
    env = standard_environment()
    macroexpand_source(
        """
        (macro with-temp (expr)
          (cons 'let
            (cons
              (cons (cons 'tmp (cons 1 '())) '())
              (cons expr '()))))
        """,
        env,
    )

    expansion = macroexpand_source("(with-temp tmp)", env)

    assert expansion.ok
    assert len(expansion.traces) == 1
    assert len(expansion.traces[0].renames) == 1
    rename = expansion.traces[0].renames[0]
    assert rename.original == Symbol("tmp")
    assert rename.kind == "binding"
    assert rename.rewritten.name.startswith("__qy_hygiene_binding_tmp_")
    assert expansion.source_map[0].renames == expansion.traces[0].renames


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


def test_macroexpand_reports_stable_compile_time_evaluation_errors():
    env = standard_environment()
    macroexpand_source("(macro bad () (missing 1))", env)

    expansion = macroexpand_source("(bad)", env)

    assert not expansion.ok
    assert "failed during compile-time evaluation" in expansion.diagnostics[0].message
    assert "macro 'bad'" in expansion.diagnostics[0].message


def test_macroexpand_reports_nested_expansion_chain_on_error():
    env = standard_environment()
    macroexpand_source(
        """
        (macro inner () (missing 1))
        (macro outer () '(inner))
        """,
        env,
    )

    expansion = macroexpand_source("(outer)", env)

    assert not expansion.ok
    assert "expansion chain: outer -> inner" in expansion.diagnostics[0].message


def test_macroexpand_nested_gensym_symbols_do_not_conflict():
    env = standard_environment()
    macroexpand_source(
        """
        (macro inner () (gensym 'tmp))
        (macro outer () '(inner))
        """,
        env,
    )

    expansion = macroexpand_source("(outer)\n(outer)", env)

    assert expansion.ok
    assert isinstance(expansion.forms[0], Symbol)
    assert isinstance(expansion.forms[1], Symbol)
    assert expansion.forms[0] != expansion.forms[1]


def test_macroexpand_macro_namespace_does_not_overwrite_runtime_binding():
    env = standard_environment()
    env.define(Symbol("const-answer"), 7)

    macroexpand_source("(macro const-answer () 42)", env)

    assert env.resolve(Symbol("const-answer")) == 7
    expansion = macroexpand_source("(const-answer)", env)
    assert expansion.ok
    assert expansion.forms == [42]


def test_macroexpand_keeps_module_macro_scope_inside_module_body():
    expansion = macroexpand_source(
        """
        (module tools
          (macro const-answer () 42)
          (const-answer))
        """
    )

    assert expansion.ok
    module_form = expansion.forms[0]
    assert isinstance(module_form, tuple)
    assert module_form[3] == 42


def test_macroexpand_imports_exported_module_macros_without_runtime_binding_pollution():
    env = standard_environment()
    register_module(
        StandardModule(
            "test.macros",
            {Symbol("runtime-answer"): 7},
            {
                Symbol("const-answer"): MacroDefinition(
                    Symbol("const-answer"),
                    (),
                    (42,),
                    env,
                )
            },
        )
    )

    expansion = macroexpand_source(
        """
        (from test.macros import const-answer)
        (const-answer)
        """,
        env,
    )

    assert expansion.ok
    assert expansion.forms[1] == 42
    with pytest.raises(EvaluationError):
        env.resolve(Symbol("const-answer"))


def test_macroexpand_imports_module_macros_inside_module_imports_block():
    env = standard_environment()
    register_module(
        StandardModule(
            "test.macros.inner",
            {},
            {
                Symbol("const-answer"): MacroDefinition(
                    Symbol("const-answer"),
                    (),
                    (42,),
                    env,
                )
            },
        )
    )

    expansion = macroexpand_source(
        """
        (module consumer
          (imports
            (from test.macros.inner import const-answer))
          (const-answer))
        """,
        env,
    )

    assert expansion.ok
    module_form = expansion.forms[0]
    assert isinstance(module_form, tuple)
    assert module_form[3] == 42
