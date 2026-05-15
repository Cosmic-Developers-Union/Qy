from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefineExpr
from qy.ir import LambdaExpr
from qy.ir import LetExpr
from qy.ir import LiteralExpr
from qy.ir import QuoteExpr
from qy.ir import SymbolRefExpr
from qy.lowering import lower_source
from qy.reader import Symbol


def test_lowering_keeps_default_literals_after_symbol_resolution():
    program = lower_source("(+ 1 2)")

    assert program.ok
    call = program.body[0]
    assert isinstance(call, CallExpr)
    assert all(isinstance(arg, LiteralExpr) for arg in call.args)
    assert [arg.value for arg in call.args if isinstance(arg, LiteralExpr)] == [1, 2]


def test_lexical_binding_wins_over_default_literal_symbol():
    program = lower_source("(let ((1 10)) (+ 1 2))")

    assert program.ok
    let = program.body[0]
    assert isinstance(let, LetExpr)
    call = let.body[0]
    assert isinstance(call, CallExpr)

    rebound_one = call.args[0]
    default_two = call.args[1]

    assert isinstance(rebound_one, SymbolRefExpr)
    assert rebound_one.symbol.name == "1"
    assert rebound_one.binding.source == "local"
    assert rebound_one.type_name == "number"

    assert isinstance(default_two, LiteralExpr)
    assert default_two.value == 2
    assert default_two.source_symbol is not None
    assert default_two.source_symbol.name == "2"


def test_quote_lowers_to_raw_ast_boundary():
    program = lower_source("(quote (+ 1 2))")

    assert program.ok
    quote = program.body[0]
    assert isinstance(quote, QuoteExpr)
    assert isinstance(quote.form, tuple)
    assert isinstance(quote.form[0], Symbol)
    assert quote.form[0].name == "+"


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
