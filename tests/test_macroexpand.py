from qy.evaluator import standard_environment
from qy.macroexpand import macroexpand_source
from qy.reader import Symbol


def test_macroexpand_expands_bound_macro_call():
    env = standard_environment()
    macroexpand_source("(macro const-answer (ignored) '(+ 20 22))", env)

    expansion = macroexpand_source("(const-answer missing)", env)

    assert expansion.ok
    assert expansion.forms == [(Symbol("+"), Symbol("20"), Symbol("22"))]


def test_macroexpand_keeps_quote_boundary():
    expansion = macroexpand_source("'(const-answer missing)")

    assert expansion.ok
    assert expansion.forms == [(Symbol("quote"), (Symbol("const-answer"), Symbol("missing")))]
