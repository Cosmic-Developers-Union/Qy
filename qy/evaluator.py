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
    "Primitive",
    "evaluate",
    "evaluate_file",
    "evaluate_program",
    "evaluate_source",
    "standard_environment",
]


@dataclass(frozen=True, slots=True)
class Primitive:
    name: str
    func: Callable[..., object]

    def __call__(self, *args: object) -> object:
        return self.func(*args)


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


def standard_environment() -> Environment:
    return Environment(
        {
            Symbol("+"): Primitive("+", _add),
            Symbol("-"): Primitive("-", _sub),
            Symbol("*"): Primitive("*", _mul),
            Symbol("/"): Primitive("/", _div),
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
    arguments = [evaluate(argument, env) for argument in argument_expressions]

    if isinstance(operator_value, Primitive):
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
