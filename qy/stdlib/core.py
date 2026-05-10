# coding: utf-8

from __future__ import annotations

import operator

from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import EvaluationOperator
from qy.evaluator import PureOperator
from qy.evaluator import SyntaxOperator
from qy.evaluator import UserFunction
from qy.evaluator import ensure_symbol
from qy.evaluator import evaluate
from qy.evaluator import evaluate_body
from qy.reader import Symbol
from qy.stdlib.imports import parse_from_import
from qy.stdlib.module import StandardModule


def module() -> StandardModule:
    return StandardModule(
        "qy.core",
        {
            Symbol("+"): PureOperator("+", _add, "Add numbers."),
            Symbol("-"): PureOperator("-", _sub, "Subtract numbers, or negate one number."),
            Symbol("*"): PureOperator("*", _mul, "Multiply numbers."),
            Symbol("/"): PureOperator("/", _div, "Divide numbers, or invert one number."),
            Symbol("atom"): PureOperator(
                "atom", _atom, "Return true if the value is not a non-empty list."
            ),
            Symbol("car"): PureOperator("car", _car, "Return the first item of a non-empty list."),
            Symbol("cdr"): PureOperator(
                "cdr", _cdr, "Return all but the first item of a non-empty list."
            ),
            Symbol("cond"): EvaluationOperator(
                "cond", _cond, "Evaluate the first truthy condition branch."
            ),
            Symbol("cons"): PureOperator("cons", _cons, "Prepend an item to a list."),
            Symbol("defun"): SyntaxOperator(
                "defun", _defun, "Define a function in the current environment."
            ),
            Symbol("eq"): PureOperator("eq", _eq, "Compare atoms and empty lists."),
            Symbol("from"): SyntaxOperator(
                "from", _from_import, "Import standard module operators into the current scope."
            ),
            Symbol("let"): EvaluationOperator(
                "let", _let, "Evaluate a body in a local lexical scope."
            ),
            Symbol("quote"): EvaluationOperator(
                "quote", _quote, "Return one expression without evaluating it."
            ),
        },
    )


def _ensure_number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationError(f"expected number, got {value!r}")
    return value


def _ensure_tuple(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise EvaluationError(f"expected tuple, got {value!r}")
    return value


def _truthy(value: object) -> bool:
    return value not in (False, None, ())


def _add(*args: object) -> int | float:
    return sum(_ensure_number(arg) for arg in args)


def _sub(first: object, *rest: object) -> int | float:
    first_number = _ensure_number(first)
    if not rest:
        return -first_number
    return first_number - sum(_ensure_number(arg) for arg in rest)


def _mul(*args: object) -> int | float:
    result: int | float = 1
    for arg in args:
        result = operator.mul(result, _ensure_number(arg))
    return result


def _div(first: object, *rest: object) -> int | float:
    result = _ensure_number(first)
    if not rest:
        return 1 / result
    for arg in rest:
        result = operator.truediv(result, _ensure_number(arg))
    return result


def _quote(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        raise EvaluationError("quote expects exactly one argument")
    return args[0]


def _atom(value: object) -> bool:
    return not isinstance(value, tuple) or len(value) == 0


def _eq(left: object, right: object) -> bool:
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == 0 and len(right) == 0
    return left == right


def _car(value: object) -> object:
    items = _ensure_tuple(value)
    if not items:
        raise EvaluationError("car expects a non-empty tuple")
    return items[0]


def _cdr(value: object) -> tuple[object, ...]:
    items = _ensure_tuple(value)
    if not items:
        raise EvaluationError("cdr expects a non-empty tuple")
    return items[1:]


def _cons(head: object, tail: object) -> tuple[object, ...]:
    return (head, *_ensure_tuple(tail))


def _cond(args: tuple[object, ...], env: Environment) -> object:
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            raise EvaluationError(f"cond clause must be a pair, got {clause!r}")
        condition, result = clause
        if _truthy(evaluate(condition, env)):
            return evaluate(result, env)
    return None


def _let(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 2:
        raise EvaluationError("let expects bindings and at least one body expression")

    bindings, *body = args
    if not isinstance(bindings, tuple):
        raise EvaluationError(f"let bindings must be a list, got {bindings!r}")

    local_env = env.child()
    for binding in bindings:
        if not isinstance(binding, tuple) or len(binding) != 2:
            raise EvaluationError(f"let binding must be a pair, got {binding!r}")
        name, expression = binding
        local_env.define(ensure_symbol(name, "let binding name"), evaluate(expression, local_env))

    return evaluate_body(tuple(body), local_env)


def _defun(expression: tuple[object, ...], env: Environment) -> object:
    if len(expression) < 4:
        raise EvaluationError("defun expects a name, parameter list, and body")

    _, name, params, *body = expression
    name = ensure_symbol(name, "defun name")
    if not isinstance(params, tuple):
        raise EvaluationError(f"defun parameters must be a tuple of symbols, got {params!r}")

    param_symbols = tuple(_ensure_symbol_parameter(param) for param in params)
    function = UserFunction(name, param_symbols, tuple(body), env)
    return env.define(name, function)


def _from_import(expression: tuple[object, ...], env: Environment) -> object:
    try:
        module_name, specs = parse_from_import(expression)
        from qy.stdlib import load_module

        source_module = load_module(module_name.name)
        for spec in specs:
            env.define(spec.alias, source_module.resolve(spec.name))
    except (KeyError, ValueError) as e:
        raise EvaluationError(str(e)) from e

    return None


def _ensure_symbol_parameter(value: object) -> Symbol:
    if not isinstance(value, Symbol):
        raise EvaluationError(f"defun parameters must be symbols, got {value!r}")
    return value
