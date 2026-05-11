# coding: utf-8

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable
from collections.abc import Coroutine
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from typing import cast

from qy.reader import Symbol
from qy.reader import read
from qy.reader import read_one

__all__ = [
    "ComponentDefinition",
    "ControlOperator",
    "EffectOperator",
    "Environment",
    "EvaluationError",
    "EvaluationOperator",
    "MacroDefinition",
    "MetaOperator",
    "PureOperator",
    "ScopeOperator",
    "SyntaxOperator",
    "UserFunction",
    "ensure_symbol",
    "evaluate",
    "evaluate_async",
    "evaluate_body",
    "evaluate_body_async",
    "evaluate_file",
    "evaluate_file_async",
    "evaluate_program",
    "evaluate_program_async",
    "evaluate_source",
    "evaluate_source_async",
    "run_async",
    "standard_environment",
]

OperatorKind = Literal["pure", "scope", "control", "effect", "meta"]
ArgumentEvaluator = Callable[[tuple[object, ...], "Environment"], object]


@dataclass(frozen=True, slots=True)
class PureOperator:
    name: str
    func: Callable[..., object]
    doc: str = ""
    argument_evaluator: ArgumentEvaluator | None = None

    @property
    def kind(self) -> OperatorKind:
        return "pure"

    def __call__(self, *args: object) -> object:
        return self.func(*args)


@dataclass(frozen=True, slots=True)
class ScopeOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]
    doc: str = ""

    @property
    def kind(self) -> OperatorKind:
        return "scope"

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class ControlOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]
    doc: str = ""

    @property
    def kind(self) -> OperatorKind:
        return "control"

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class EffectOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]
    doc: str = ""

    @property
    def kind(self) -> OperatorKind:
        return "effect"

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class MetaOperator:
    name: str
    func: Callable[[tuple[object, ...], Environment], object]
    doc: str = ""

    @property
    def kind(self) -> OperatorKind:
        return "meta"

    def __call__(self, expression: tuple[object, ...], env: Environment) -> object:
        return self.func(expression, env)


EvaluationOperator = ControlOperator
SyntaxOperator = MetaOperator


@dataclass(frozen=True, slots=True)
class UserFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        if len(args) != len(self.params):
            raise EvaluationError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}"
            )
        local_env = Environment(dict(zip(self.params, args, strict=True)), self.closure)
        return await evaluate_body_async(self.body, local_env)


@dataclass(frozen=True, slots=True)
class ComponentDefinition:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        if len(args) != len(self.params):
            raise EvaluationError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}"
            )
        local_env = Environment(dict(zip(self.params, args, strict=True)), self.closure)
        return await evaluate_body_async(self.body, local_env)


@dataclass(frozen=True, slots=True)
class MacroDefinition:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def expand(self, args: tuple[object, ...]) -> object:
        if len(args) != len(self.params):
            raise EvaluationError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}"
            )
        local_env = Environment(dict(zip(self.params, args, strict=True)), self.closure)
        return await evaluate_body_async(self.body, local_env)


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
        self._cache: dict[object, object] = parent._cache if parent is not None else {}

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

    def local_bindings(self) -> dict[Symbol, object]:
        return dict(self._bindings)

    def cache_lookup(self, key: object) -> object:
        return self._cache[key]

    def cache_define(self, key: object, value: object) -> object:
        self._cache[key] = value
        return value

    def cache_discard(self, key: object) -> None:
        self._cache.pop(key, None)

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
        argument_evaluator: ArgumentEvaluator | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | Callable[..., object]:
        def register(func: Callable[..., object]) -> Callable[..., object]:
            self.define(Symbol(name), PureOperator(name, func, doc, argument_evaluator))
            return func

        if func is None:
            return register
        return register(func)

    def register_scope(
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
            self.define(Symbol(name), ScopeOperator(name, func, doc))
            return func

        if func is None:
            return register
        return register(func)

    def register_control(
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
            self.define(Symbol(name), ControlOperator(name, func, doc))
            return func

        if func is None:
            return register
        return register(func)

    def register_effect(
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
            self.define(Symbol(name), EffectOperator(name, func, doc))
            return func

        if func is None:
            return register
        return register(func)

    def register_meta(
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
            self.define(Symbol(name), MetaOperator(name, func, doc))
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
        return self.register_control(name, func, doc=doc)

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
        return self.register_meta(name, func, doc=doc)


def standard_environment() -> Environment:
    from qy.stdlib import standard_bindings

    return Environment(standard_bindings())


def evaluate(expression: object, env: Environment | None = None) -> object:
    return run_async(evaluate_async(expression, env))


async def evaluate_async(expression: object, env: Environment | None = None) -> object:
    env = env or standard_environment()

    if isinstance(expression, Symbol):
        return env.resolve(expression)
    if not isinstance(expression, tuple):
        return expression
    if not expression:
        raise EvaluationError("cannot evaluate empty expression")

    operator_expression, *argument_expressions = expression
    operator_value = await evaluate_async(operator_expression, env)

    if isinstance(operator_value, MetaOperator):
        return await _await_if_needed(operator_value(expression, env))
    if isinstance(operator_value, ScopeOperator | ControlOperator | EffectOperator):
        return await _await_if_needed(operator_value(tuple(argument_expressions), env))
    if isinstance(operator_value, MacroDefinition):
        expanded = await operator_value.expand(tuple(argument_expressions))
        return await evaluate_async(expanded, env)
    if isinstance(operator_value, PureOperator):
        arguments = await _evaluate_pure_arguments_async(
            operator_value, tuple(argument_expressions), env
        )
        return await _await_if_needed(operator_value(*arguments))
    if isinstance(operator_value, UserFunction | ComponentDefinition):
        arguments = [await evaluate_async(argument, env) for argument in argument_expressions]
        return await _await_if_needed(operator_value(*arguments))
    raise EvaluationError(f"{operator_expression!r} resolved to non-callable {operator_value!r}")


def evaluate_source(source: str, env: Environment | None = None) -> object:
    return run_async(evaluate_source_async(source, env))


async def evaluate_source_async(source: str, env: Environment | None = None) -> object:
    return await evaluate_async(read_one(source), env)


def evaluate_program(source: str, env: Environment | None = None) -> list[object]:
    return cast(list[object], run_async(evaluate_program_async(source, env)))


async def evaluate_program_async(source: str, env: Environment | None = None) -> list[object]:
    env = env or standard_environment()
    return [await evaluate_async(form, env) for form in read(source)]


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    return run_async(evaluate_file_async(path, env))


async def evaluate_file_async(path: str | Path, env: Environment | None = None) -> object:
    source = Path(path).read_text(encoding="utf-8")
    results = await evaluate_program_async(source, env)
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
    return run_async(evaluate_body_async(body, env))


async def evaluate_body_async(body: tuple[object, ...], env: Environment) -> object:
    if not body:
        raise EvaluationError("body must contain at least one expression")
    result = None
    for expression in body:
        result = await evaluate_async(expression, env)
    return result


def ensure_symbol(value: object, context: str) -> Symbol:
    if not isinstance(value, Symbol):
        raise EvaluationError(f"{context} must be a symbol, got {value!r}")
    return value


async def _evaluate_pure_arguments_async(
    operator: PureOperator,
    argument_expressions: tuple[object, ...],
    env: Environment,
) -> tuple[object, ...]:
    if operator.argument_evaluator is not None:
        arguments = await _await_if_needed(operator.argument_evaluator(argument_expressions, env))
        if not isinstance(arguments, tuple):
            raise EvaluationError(
                f"{operator.name} argument evaluator must return a tuple, got {arguments!r}"
            )
        return arguments
    return tuple([await evaluate_async(argument, env) for argument in argument_expressions])


async def _await_if_needed(value: object) -> object:
    if inspect.iscoroutine(value):
        return await value
    return value


def run_async(awaitable: object) -> object:
    if not inspect.isawaitable(awaitable):
        return awaitable
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(cast(Coroutine[object, object, object], awaitable))

    result: object = None
    error: BaseException | None = None

    def run_in_thread() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(cast(Coroutine[object, object, object], awaitable))
        except BaseException as e:
            error = e

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        raise error
    return result
