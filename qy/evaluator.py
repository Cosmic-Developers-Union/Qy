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

from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyCancelledError
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
from qy.errors import QyError
from qy.errors import QyResolveError
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.errors import TraceFrame
from qy.reader import DottedTuple
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.reader import read_one
from qy.values import QY_EMPTY_LIST
from qy.values import QyCons
from qy.values import qy_cons_to_tuple

__all__ = [
    "QY_EMPTY_LIST",
    "ComponentDefinition",
    "ControlOperator",
    "EffectDefinition",
    "EffectOperator",
    "Environment",
    "EvaluationError",
    "EvaluationOperator",
    "HostObjectRef",
    "MacroDefinition",
    "MetaOperator",
    "PureOperator",
    "QyCons",
    "QyContinuation",
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
class EffectDefinition:
    name: Symbol
    resumable: bool = True
    doc: str = ""


@dataclass(slots=True)
class QyContinuation:
    effect: str
    resumable: bool
    _resume: Callable[[object], object]

    async def resume(self, value: object) -> object:
        if not self.resumable:
            raise QyEffectError(
                f"effect {self.effect!r} is not resumable",
                metadata={"effect": self.effect, "value": value},
            )
        return await _await_if_needed(self._resume(value))


@dataclass(frozen=True, slots=True)
class UserFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        if len(args) != len(self.params):
            raise QyArityError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}",
                span=self.name.span,
                metadata={
                    "expected": len(self.params),
                    "actual": len(args),
                    "function": self.name.name,
                },
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
            raise QyArityError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}",
                span=self.name.span,
                metadata={
                    "expected": len(self.params),
                    "actual": len(args),
                    "component": self.name.name,
                },
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
            raise QyArityError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}",
                span=self.name.span,
                metadata={
                    "expected": len(self.params),
                    "actual": len(args),
                    "macro": self.name.name,
                },
            )
        local_env = Environment(dict(zip(self.params, args, strict=True)), self.closure)
        return await evaluate_body_async(self.body, local_env)


@dataclass(frozen=True, slots=True, eq=False)
class HostObjectRef:
    value: object


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
    if expression is QY_EMPTY_LIST:
        return expression
    if isinstance(expression, QyCons):
        try:
            expression = qy_cons_to_tuple(expression)
        except TypeError as e:
            raise QyRuntimeError(
                "cannot evaluate an improper Qy cons list as a call",
                span=get_span(expression),
                cause=e,
            ) from e
    if not isinstance(expression, tuple):
        return expression
    span = get_span(expression)
    if isinstance(expression, DottedTuple):
        raise QyRuntimeError("cannot evaluate dotted form as a call", span=span)
    if not expression:
        raise QyRuntimeError("cannot evaluate empty expression", span=span)

    operator_expression, *argument_expressions = expression
    if isinstance(operator_expression, Symbol):
        if operator_expression.name == "perform":
            return await _evaluate_perform_form(tuple(argument_expressions), env, span)
        if operator_expression.name == "handle":
            return await _evaluate_handle_form(tuple(argument_expressions), env, span)
        if operator_expression.name == "resume":
            return await _evaluate_resume_form(tuple(argument_expressions), env, span)
        if operator_expression.name == "assert":
            return await _evaluate_assert_form(tuple(argument_expressions), env, span)

    operator_value: object | None = None
    try:
        try:
            operator_value = await evaluate_async(operator_expression, env)
        except QyEffectSignal as e:
            _compose_effect_continuation(
                e,
                lambda resumed_operator: _apply_operator(
                    operator_expression,
                    resumed_operator,
                    tuple(argument_expressions),
                    env,
                    span,
                ),
            )
            raise

        return await _apply_operator(
            operator_expression,
            operator_value,
            tuple(argument_expressions),
            env,
            span,
        )
    except QyEffectSignal as e:
        e.set_span_if_missing(span)
        e.add_frame(_trace_frame(operator_expression, operator_value, span))
        raise
    except QyError as e:
        e.set_span_if_missing(span)
        e.add_frame(_trace_frame(operator_expression, operator_value, span))
        raise
    except asyncio.CancelledError as e:
        qy_error = QyCancelledError(
            "evaluation cancelled",
            span=span,
            cause=e,
        )
        qy_error.add_frame(_trace_frame(operator_expression, operator_value, span))
        raise qy_error from e
    except Exception as e:
        qy_error = QyRuntimeError(
            str(e),
            span=span,
            cause=e,
            metadata={"python_exception": type(e).__name__},
        )
        qy_error.add_frame(_trace_frame(operator_expression, operator_value, span))
        raise qy_error from e


def evaluate_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    return run_async(evaluate_source_async(source, env, source_name=source_name))


async def evaluate_source_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    return await evaluate_async(read_one(source, source_name=source_name), env)


def evaluate_program(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    return cast(
        list[object],
        run_async(evaluate_program_async(source, env, source_name=source_name)),
    )


async def evaluate_program_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    env = env or standard_environment()
    return [await evaluate_async(form, env) for form in read(source, source_name=source_name)]


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    return run_async(evaluate_file_async(path, env))


async def evaluate_file_async(path: str | Path, env: Environment | None = None) -> object:
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    results = await evaluate_program_async(source, env, source_name=str(path))
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
    raise QyResolveError(
        f"unresolved symbol {symbol.name!r}",
        span=symbol.span,
        metadata={"symbol": symbol.name},
    )


def evaluate_body(body: tuple[object, ...], env: Environment) -> object:
    return run_async(evaluate_body_async(body, env))


async def evaluate_body_async(body: tuple[object, ...], env: Environment) -> object:
    if not body:
        raise QyArityError("body must contain at least one expression")
    return await _evaluate_body_from(body, 0, env)


async def _evaluate_body_from(
    body: tuple[object, ...],
    index: int,
    env: Environment,
) -> object:
    result = None
    for current in range(index, len(body)):
        try:
            result = await evaluate_async(body[current], env)
        except QyEffectSignal as e:
            _compose_effect_continuation(
                e,
                lambda resumed, next_index=current + 1: _continue_body_after_resume(
                    body,
                    next_index,
                    resumed,
                    env,
                ),
            )
            raise
    return result


async def _continue_body_after_resume(
    body: tuple[object, ...],
    index: int,
    resumed: object,
    env: Environment,
) -> object:
    if index >= len(body):
        return resumed
    return await _evaluate_body_from(body, index, env)


def ensure_symbol(value: object, context: str) -> Symbol:
    if not isinstance(value, Symbol):
        raise QyTypeError(
            f"{context} must be a symbol, got {value!r}",
            span=get_span(value),
            metadata={"context": context, "value": value},
        )
    return value


async def _evaluate_pure_arguments_async(
    operator: PureOperator,
    argument_expressions: tuple[object, ...],
    env: Environment,
) -> tuple[object, ...]:
    if operator.argument_evaluator is not None:
        arguments = await _await_if_needed(operator.argument_evaluator(argument_expressions, env))
        if not isinstance(arguments, tuple):
            raise QyTypeError(
                f"{operator.name} argument evaluator must return a tuple, got {arguments!r}",
                metadata={"operator": operator.name, "value": arguments},
            )
        return arguments
    return tuple([await evaluate_async(argument, env) for argument in argument_expressions])


async def _await_if_needed(value: object) -> object:
    if inspect.iscoroutine(value):
        return await value
    return value


async def _apply_operator(
    operator_expression: object,
    operator_value: object,
    argument_expressions: tuple[object, ...],
    env: Environment,
    span: SourceSpan | None,
) -> object:
    if isinstance(operator_value, MetaOperator):
        return await _await_if_needed(
            operator_value((operator_expression, *argument_expressions), env)
        )
    if isinstance(operator_value, ScopeOperator | ControlOperator | EffectOperator):
        return await _await_if_needed(operator_value(argument_expressions, env))
    if isinstance(operator_value, MacroDefinition):
        try:
            expanded = await operator_value.expand(argument_expressions)
        except QyEffectSignal as e:
            _compose_effect_continuation(e, lambda expanded: evaluate_async(expanded, env))
            raise
        return await evaluate_async(expanded, env)
    if isinstance(operator_value, PureOperator):
        if operator_value.argument_evaluator is not None:
            try:
                arguments = await _evaluate_pure_arguments_async(
                    operator_value, argument_expressions, env
                )
            except QyEffectSignal as e:
                _compose_effect_continuation(
                    e,
                    lambda arguments: _await_if_needed(
                        operator_value(*cast(tuple[object, ...], arguments))
                    ),
                )
                raise
            return await _await_if_needed(operator_value(*arguments))
        return await _evaluate_values(
            argument_expressions,
            env,
            lambda arguments: _await_if_needed(operator_value(*arguments)),
        )
    if isinstance(operator_value, UserFunction | ComponentDefinition):
        return await _evaluate_values(
            argument_expressions,
            env,
            lambda arguments: _await_if_needed(operator_value(*arguments)),
        )
    raise QyTypeError(
        f"{operator_expression!r} resolved to non-callable {operator_value!r}",
        span=get_span(operator_expression) or span,
        metadata={"operator": operator_value},
    )


async def _evaluate_values(
    expressions: tuple[object, ...],
    env: Environment,
    then: Callable[[tuple[object, ...]], object],
) -> object:
    return await _evaluate_values_from(expressions, 0, (), env, then)


async def _evaluate_values_from(
    expressions: tuple[object, ...],
    index: int,
    values: tuple[object, ...],
    env: Environment,
    then: Callable[[tuple[object, ...]], object],
) -> object:
    if index >= len(expressions):
        return await _await_if_needed(then(values))
    try:
        value = await evaluate_async(expressions[index], env)
    except QyEffectSignal as e:
        _compose_effect_continuation(
            e,
            lambda resumed: _evaluate_values_from(
                expressions,
                index + 1,
                (*values, resumed),
                env,
                then,
            ),
        )
        raise
    return await _evaluate_values_from(expressions, index + 1, (*values, value), env, then)


async def _evaluate_perform_form(
    args: tuple[object, ...], env: Environment, span: SourceSpan | None
) -> object:
    if len(args) != 2:
        raise QyArityError(
            f"perform expects exactly two arguments, got {len(args)}",
            span=span,
            metadata={"expected": 2, "actual": len(args)},
        )
    effect_name = _effect_name(args[0])
    definition = _resolve_effect_definition(effect_name, env, span)
    try:
        arg = await evaluate_async(args[1], env)
    except QyEffectSignal as e:
        _compose_effect_continuation(
            e,
            lambda resumed: _raise_effect_signal(effect_name, resumed, definition.resumable, span),
        )
        raise
    return await _raise_effect_signal(effect_name, arg, definition.resumable, span)


async def _raise_effect_signal(
    effect_name: str,
    arg: object,
    resumable: bool,
    span: SourceSpan | None,
) -> object:
    raise QyEffectSignal(
        effect_name,
        arg,
        _identity_continuation(effect_name, resumable),
        resumable=resumable,
        span=span,
    )


async def _evaluate_handle_form(
    args: tuple[object, ...], env: Environment, span: SourceSpan | None
) -> object:
    if len(args) != 2:
        raise QyArityError(
            f"handle expects exactly two arguments, got {len(args)}",
            span=span,
            metadata={"expected": 2, "actual": len(args)},
        )
    expr, handler_form = args
    handlers = _parse_effect_handlers(handler_form)
    try:
        return await evaluate_async(expr, env)
    except QyEffectSignal as e:
        return await _handle_effect_signal(e, handlers, env)


async def _handle_effect_signal(
    signal: QyEffectSignal,
    handlers: Mapping[str, tuple[Symbol, Symbol, tuple[object, ...]]],
    env: Environment,
) -> object:
    try:
        arg_name, continuation_name, body = handlers[signal.effect]
    except KeyError:
        raise signal from None
    local_env = env.child(
        {
            arg_name: signal.arg,
            continuation_name: signal.continuation,
        }
    )
    try:
        return await evaluate_body_async(body, local_env)
    except QyEffectSignal as nested:
        return await _handle_effect_signal(nested, handlers, env)


async def _evaluate_resume_form(
    args: tuple[object, ...], env: Environment, span: SourceSpan | None
) -> object:
    if len(args) != 2:
        raise QyArityError(
            f"resume expects exactly two arguments, got {len(args)}",
            span=span,
            metadata={"expected": 2, "actual": len(args)},
        )
    continuation = await evaluate_async(args[0], env)
    if not isinstance(continuation, QyContinuation):
        raise QyTypeError(
            f"resume expects a continuation, got {continuation!r}",
            span=get_span(args[0]) or span,
            metadata={"value": continuation},
        )
    value = await evaluate_async(args[1], env)
    return await continuation.resume(value)


async def _evaluate_assert_form(
    args: tuple[object, ...], env: Environment, span: SourceSpan | None
) -> object:
    if len(args) not in {1, 2}:
        raise QyArityError(
            f"assert expects one or two arguments, got {len(args)}",
            span=span,
            metadata={"expected": "1..2", "actual": len(args)},
        )
    try:
        condition = await evaluate_async(args[0], env)
    except QyEffectSignal as e:
        _compose_effect_continuation(
            e,
            lambda resumed: _finish_assert_form(args, env, span, resumed),
        )
        raise
    return await _finish_assert_form(args, env, span, condition)


async def _finish_assert_form(
    args: tuple[object, ...],
    env: Environment,
    span: SourceSpan | None,
    condition: object,
) -> object:
    if _truthy(condition):
        return condition

    if len(args) == 1:
        message: object = Symbol("assertion failed")
    else:
        try:
            message = await _evaluate_assert_message(args[1], env)
        except QyEffectSignal as e:
            _compose_effect_continuation(
                e,
                lambda resumed: _raise_assert_failed(resumed, condition, span),
            )
            raise
    return await _raise_assert_failed(message, condition, get_span(args[0]) or span)


async def _evaluate_assert_message(expression: object, env: Environment) -> object:
    if isinstance(expression, Symbol):
        try:
            return await evaluate_async(expression, env)
        except EvaluationError:
            return expression
    return await evaluate_async(expression, env)


async def _raise_assert_failed(
    message: object,
    condition: object,
    span: SourceSpan | None,
) -> object:
    raise QyEffectSignal(
        "assert-failed",
        message,
        _identity_continuation("assert-failed", False),
        resumable=False,
        span=span,
        metadata={"condition": condition},
    )


def _truthy(value: object) -> bool:
    return value not in (False, None, ())


def _parse_effect_handlers(
    handler_form: object,
) -> dict[str, tuple[Symbol, Symbol, tuple[object, ...]]]:
    if not isinstance(handler_form, tuple):
        raise QyTypeError(
            f"handle clauses must be a tuple, got {handler_form!r}",
            span=get_span(handler_form),
        )
    handlers: dict[str, tuple[Symbol, Symbol, tuple[object, ...]]] = {}
    for clause in handler_form:
        if not isinstance(clause, tuple) or len(clause) < 3:
            raise QyTypeError(
                f"handle clause must be (effect (arg k) body...), got {clause!r}",
                span=get_span(clause),
            )
        effect, params, *body = clause
        effect_name = _effect_name(effect)
        if not isinstance(params, tuple) or len(params) != 2:
            raise QyTypeError(
                f"handle clause parameters must be (arg k), got {params!r}",
                span=get_span(params),
            )
        arg_name, continuation_name = params
        if not isinstance(arg_name, Symbol) or not isinstance(continuation_name, Symbol):
            raise QyTypeError(
                f"handle clause parameters must be symbols, got {params!r}",
                span=get_span(params),
            )
        if not body:
            raise QyArityError("handle clause body must contain at least one expression")
        handlers[effect_name] = (arg_name, continuation_name, tuple(body))
    return handlers


def _effect_name(value: object) -> str:
    if not isinstance(value, Symbol):
        raise QyTypeError(
            f"effect name must be a symbol, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )
    return value.name


def _resolve_effect_definition(
    effect_name: str, env: Environment, span: SourceSpan | None
) -> EffectDefinition:
    try:
        value = env.resolve(Symbol(effect_name))
    except QyError as e:
        raise QyEffectError(
            f"effect {effect_name!r} is not declared; use defeffect before perform",
            span=span,
            cause=e,
            metadata={"effect": effect_name},
        ) from e
    if not isinstance(value, EffectDefinition):
        raise QyTypeError(
            f"{effect_name!r} is not an effect definition",
            span=span,
            metadata={"effect": effect_name, "value": value},
        )
    return value


def _identity_continuation(effect_name: str, resumable: bool) -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation(effect_name, resumable, resume)


def _compose_effect_continuation(
    signal: QyEffectSignal,
    then: Callable[[object], object],
) -> None:
    previous = signal.continuation
    if not isinstance(previous, QyContinuation):
        return

    async def resume(value: object) -> object:
        previous_result = await previous.resume(value)
        return await _await_if_needed(then(previous_result))

    signal.continuation = QyContinuation(signal.effect, previous.resumable, resume)


def _trace_frame(
    operator_expression: object,
    operator_value: object | None,
    span: SourceSpan | None,
) -> TraceFrame:
    if isinstance(operator_value, ComponentDefinition):
        return TraceFrame("component", operator_value.name.name, get_span(operator_expression))
    if isinstance(operator_value, UserFunction):
        name = None if operator_value.name.name == "<lambda>" else operator_value.name.name
        kind = "lambda" if name is None else "call"
        return TraceFrame(kind, name, get_span(operator_expression))
    if isinstance(operator_value, MacroDefinition):
        return TraceFrame("macro", operator_value.name.name, get_span(operator_expression))
    if isinstance(
        operator_value,
        PureOperator | ScopeOperator | ControlOperator | EffectOperator | MetaOperator,
    ):
        return TraceFrame("operator", operator_value.name, get_span(operator_expression))
    if isinstance(operator_expression, Symbol):
        return TraceFrame("call", operator_expression.name, get_span(operator_expression))
    return TraceFrame("call", None, span)


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
