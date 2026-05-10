# coding: utf-8

from __future__ import annotations

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
    "ensure_symbol",
    "evaluate",
    "evaluate_body",
    "evaluate_file",
    "evaluate_program",
    "evaluate_source",
    "standard_environment",
]


@dataclass(frozen=True, slots=True)
class PureOperator:
    name: str
    func: Callable[..., object]
    doc: str = ""

    @property
    def kind(self) -> str:
        return "pure"

    def __call__(self, *args: object) -> object:
        return self.func(*args)


@dataclass(frozen=True, slots=True)
class EvaluationOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]
    doc: str = ""

    @property
    def kind(self) -> str:
        return "evaluation"

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class SyntaxOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]
    doc: str = ""

    @property
    def kind(self) -> str:
        return "syntax"

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
        return evaluate_body(self.body, local_env)


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

    def child(self, bindings: Mapping[Symbol, object] | None = None) -> Environment:
        return Environment(bindings, self)

    def bindings(self) -> dict[Symbol, object]:
        if self._parent is None:
            return dict(self._bindings)
        result = self._parent.bindings()
        result.update(self._bindings)
        return result

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | Callable[..., object]:
        def register(func: Callable[..., object]) -> Callable[..., object]:
            self.define(Symbol(name), PureOperator(name, func, doc))
            return func

        if func is None:
            return register
        return register(func)

    def register_evaluation(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        def register(
            func: Callable[[tuple[object, ...], Environment], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), EvaluationOperator(name, func, doc))
            return func

        if func is None:
            return register
        return register(func)

    def register_syntax(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        def register(
            func: Callable[[tuple[object, ...], Environment], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), SyntaxOperator(name, func, doc))
            return func

        if func is None:
            return register
        return register(func)


def standard_environment() -> Environment:
    from qy.stdlib import standard_bindings

    return Environment(standard_bindings())


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
    results = evaluate_program(source, env)
    if not results:
        return None
    return results[-1]


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


def evaluate_body(body: tuple[object, ...], env: Environment) -> object:
    if not body:
        raise EvaluationError("body must contain at least one expression")
    result = None
    for expression in body:
        result = evaluate(expression, env)
    return result


def ensure_symbol(value: object, context: str) -> Symbol:
    if not isinstance(value, Symbol):
        raise EvaluationError(f"{context} must be a symbol, got {value!r}")
    return value
