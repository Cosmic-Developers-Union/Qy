from qy.evaluator import MacroDefinition
from qy.evaluator import evaluate_source
from qy.evaluator import standard_environment
from qy.reader import Symbol

S = Symbol


def test_eval_evaluates_symbolic_forms():
    assert evaluate_source("(eval '(+ 20 22))") == 42
    assert evaluate_source("(let ((form '(+ 20 22))) (eval form))") == 42


def test_macro_defines_ast_transform():
    env = standard_environment()
    macro = evaluate_source("(macro identity-form (form) form)", env)

    assert isinstance(macro, MacroDefinition)
    assert evaluate_source("(identity-form (+ 20 22))", env) == 42


def test_macro_receives_unevaluated_arguments():
    env = standard_environment()
    evaluate_source("(macro const-answer (ignored) '(+ 20 22))", env)

    assert evaluate_source("(const-answer missing)", env) == 42


def test_macro_can_construct_ast_with_cons():
    env = standard_environment()
    evaluate_source("(macro twice (form) (cons '+ (cons form (cons form '()))))", env)

    assert evaluate_source("(twice (+ 1 2))", env) == 6
