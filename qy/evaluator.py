# coding: utf-8

from __future__ import annotations

import operator
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from qy.reader import Symbol
from qy.reader import read
from qy.reader import read_one

__all__ = [
    "Environment",
    "EvaluationError",
    "EvaluationOperator",
    "PureOperator",
    "SyntaxOperator",
    "UserFunction",
    "evaluate",
    "evaluate_file",
    "evaluate_program",
    "evaluate_source",
    "standard_environment",
]


@dataclass(frozen=True, slots=True)
class PureOperator:
    name: str
    func: Callable[..., object]

    def __call__(self, *args: object) -> object:
        return self.func(*args)


@dataclass(frozen=True, slots=True)
class EvaluationOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class SyntaxOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]

    def __call__(self, expression: tuple[object, ...], env: Environment) -> object:
        return self.func(expression, env)


@dataclass(frozen=True, slots=True)
class UserFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    def __call__(self, *args: object) -> object:
        if len(args) != len(self.params):
            raise EvaluationError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}"
            )
        local_env = Environment(dict(zip(self.params, args, strict=True)), self.closure)
        return _evaluate_body(self.body, local_env)


class EvaluationError(Exception):
    pass


class Environment:
    def __init__(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        parent: Environment | None = None,
    ) -> None:
        self._bindings = dict(bindings or {})
        self._parent = parent

    def resolve(self, symbol: Symbol) -> object:
        if symbol in self._bindings:
            return self._bindings[symbol]
        if self._parent is not None:
            return self._parent.resolve(symbol)
        return _resolve_builtin_literal(symbol)

    def define(self, symbol: Symbol, value: object) -> object:
        self._bindings[symbol] = value
        return value


def standard_environment() -> Environment:
    return Environment(
        {
            Symbol("+"): PureOperator("+", _add),
            Symbol("-"): PureOperator("-", _sub),
            Symbol("*"): PureOperator("*", _mul),
            Symbol("/"): PureOperator("/", _div),
            Symbol("atom"): PureOperator("atom", _atom),
            Symbol("car"): PureOperator("car", _car),
            Symbol("cdr"): PureOperator("cdr", _cdr),
            Symbol("cond"): EvaluationOperator("cond", _cond),
            Symbol("cons"): PureOperator("cons", _cons),
            Symbol("defun"): SyntaxOperator("defun", _defun),
            Symbol("eq"): PureOperator("eq", _eq),
            Symbol("quote"): EvaluationOperator("quote", _quote),
        }
    )


def evaluate(expression: object, env: Environment | None = None) -> object:
    env = env or standard_environment()

    if isinstance(expression, Symbol):
        return env.resolve(expression)
    if not isinstance(expression, tuple):
        return expression
    if not expression:
        raise EvaluationError("cannot evaluate empty expression")

    operator_expression, *argument_expressions = expression
    operator_value = evaluate(operator_expression, env)

    if isinstance(operator_value, SyntaxOperator):
        return operator_value(expression, env)
    if isinstance(operator_value, EvaluationOperator):
        return operator_value(tuple(argument_expressions), env)
    if isinstance(operator_value, PureOperator | UserFunction):
        arguments = [evaluate(argument, env) for argument in argument_expressions]
        return operator_value(*arguments)
    raise EvaluationError(f"{operator_expression!r} resolved to non-callable {operator_value!r}")


def evaluate_source(source: str, env: Environment | None = None) -> object:
    return evaluate(read_one(source), env)


def evaluate_program(source: str, env: Environment | None = None) -> list[object]:
    env = env or standard_environment()
    return [evaluate(form, env) for form in read(source)]


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    source = Path(path).read_text(encoding="utf-8")
    return evaluate_source(source, env)


def _resolve_builtin_literal(symbol: Symbol) -> object:
    if symbol.name == "true":
        return True
    if symbol.name == "false":
        return False
    if symbol.name == "nil":
        return None
    try:
        return int(symbol.name)
    except ValueError:
        pass
    try:
        return float(symbol.name)
    except ValueError:
        pass
    raise EvaluationError(f"unresolved symbol {symbol.name!r}")


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


def _evaluate_body(body: tuple[object, ...], env: Environment) -> object:
    if not body:
        raise EvaluationError("body must contain at least one expression")
    result = None
    for expression in body:
        result = evaluate(expression, env)
    return result


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


def _defun(expression: tuple[object, ...], env: Environment) -> object:
    if len(expression) < 4:
        raise EvaluationError("defun expects a name, parameter list, and body")

    _, name, params, *body = expression
    if not isinstance(name, Symbol):
        raise EvaluationError(f"defun name must be a symbol, got {name!r}")
    if not isinstance(params, tuple):
        raise EvaluationError(f"defun parameters must be a tuple of symbols, got {params!r}")

    param_symbols = tuple(_ensure_symbol_parameter(param) for param in params)
    function = UserFunction(name, param_symbols, tuple(body), env)
    return env.define(name, function)


def _ensure_symbol_parameter(value: object) -> Symbol:
    if not isinstance(value, Symbol):
        raise EvaluationError(f"defun parameters must be symbols, got {value!r}")
    return value
