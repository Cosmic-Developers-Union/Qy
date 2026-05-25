from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import is_chain
from qy.frontend.reader import Symbol
from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefeffectExpr
from qy.ir import DefineExpr
from qy.ir import LambdaExpr
from qy.ir import LetExpr
from qy.ir import QuoteExpr
from qy.ir import SymbolRefExpr
from qy.passes.hir.lower import lower_source


def test_lowering_keeps_default_literals_after_symbol_resolution():
    program = lower_source("(+ 1 2)")

    assert program.ok
    call = program.body[0]
    assert isinstance(call, CallExpr)
    # New semantics: number literals are SymbolRefExpr with a default-literal
    # binding; their value is resolved at runtime via the symbol-space chain
    # (number-ss). HIR no longer materialises literal values.
    assert all(isinstance(arg, SymbolRefExpr) for arg in call.args)
    refs = [arg for arg in call.args if isinstance(arg, SymbolRefExpr)]
    assert [ref.symbol.name for ref in refs] == ["1", "2"]
    assert all(ref.binding.source == "default-literal" for ref in refs)


def test_lexical_binding_wins_over_default_literal_symbol():
    program = lower_source("(let ((1 10)) (+ 1 2))")

    assert program.ok
    let = program.body[0]
    assert isinstance(let, LetExpr)
    call = let.body[0]
    assert isinstance(call, CallExpr)

    rebound_one = call.args[0]
    default_two = call.args[1]

    # Both arguments are SymbolRefExpr now; the rebound ``1`` carries the
    # let-binding source while the un-rebound ``2`` falls through to the
    # default-literal binding.
    assert isinstance(rebound_one, SymbolRefExpr)
    assert rebound_one.symbol.name == "1"
    assert rebound_one.binding.source == "let-binding"

    assert isinstance(default_two, SymbolRefExpr)
    assert default_two.symbol.name == "2"
    assert default_two.binding.source == "default-literal"


def test_quote_lowers_to_raw_ast_boundary():
    program = lower_source("(quote (+ 1 2))")

    assert program.ok
    quote = program.body[0]
    assert isinstance(quote, QuoteExpr)
    assert is_chain(quote.form)
    items = list(cast(Chain, quote.form))
    assert isinstance(items[0], Symbol)
    assert items[0].name == "+"


def test_tail_position_is_marked_inside_function_body():
    program = lower_source(
        """
        (defun sum (n acc)
          (cond
            ((== n 0) acc)
            (true (sum (- n 1) (+ acc n)))))
        """
    )

    assert program.ok
    definition = program.body[0]
    assert isinstance(definition, DefineExpr)
    assert isinstance(definition.value, LambdaExpr)
    cond = definition.value.body[0]
    assert isinstance(cond, CondExpr)
    recursive_call = cond.clauses[1].result
    assert isinstance(recursive_call, CallExpr)
    assert recursive_call.tail_position


def test_lowering_uses_operator_signature_argument_types():
    program = lower_source("(+ true 1)")

    assert any("expects number arguments" in item.message for item in program.diagnostics)


def test_defeffect_lowers_to_define_with_effect_value():
    program = lower_source("(defeffect ask :resumable false)")

    assert program.ok
    definition = program.body[0]
    assert isinstance(definition, DefineExpr)
    assert definition.name.name == "ask"
    assert isinstance(definition.value, DefeffectExpr)
    assert definition.value.resumable is False
