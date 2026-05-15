# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from qy.async_runtime import run_async
from qy.continuation import QyContinuation
from qy.continuation import _await_if_needed
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
from qy.errors import QyError
from qy.errors import QyResolveError
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.errors import TraceFrame
from qy.macro import MacroDefinition

# Re-export sub-module symbols for backward compatibility.
from qy.operators import ArgumentEvaluator  # noqa: F401
from qy.operators import ControlOperator
from qy.operators import EffectOperator
from qy.operators import EvaluationOperator
from qy.operators import MetaOperator
from qy.operators import PureOperator
from qy.operators import ScopeOperator
from qy.operators import SyntaxOperator
from qy.reader import Form
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.runtime_values import EffectDefinition
from qy.runtime_values import HostObjectRef
from qy.runtime_values import UserFunction
from qy.runtime_values import _TailCall
from qy.values import QY_EMPTY_CHAIN
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyChain
from qy.values import QyCons

__all__ = [
    "QY_EMPTY_CHAIN",
    "QY_EMPTY_LIST",
    "QY_NIL",
    "QY_T",
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
    "QyChain",
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


def evaluate(expression: object, env: Environment | None = None) -> object:
    return run_async(evaluate_async(expression, env))


async def evaluate_async(expression: object, env: Environment | None = None) -> object:
    runtime_env = env or standard_environment()
    if isinstance(expression, Symbol):
        return runtime_env.resolve(expression)
    results = await _evaluate_ir_forms_async([cast(Form, expression)], runtime_env)
    return None if not results else results[-1]


def evaluate_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    return run_async(evaluate_source_async(source, env, source_name=source_name))


async def evaluate_source_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    results = await _evaluate_ir_forms_async(read(source, source_name=source_name), env)
    return None if not results else results[-1]


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
    return await _evaluate_ir_forms_async(read(source, source_name=source_name), env)


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    return run_async(evaluate_file_async(path, env))


async def evaluate_file_async(path: str | Path, env: Environment | None = None) -> object:
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    results = await evaluate_program_async(source, env, source_name=str(path))
    if not results:
        return None
    return results[-1]


async def _evaluate_ir_forms_async(
    forms: list[Form],
    env: Environment | None = None,
) -> list[object]:
    runtime_env = env or standard_environment()

    from qy.bytecode_compiler import compile_bytecode
    from qy.lowering import lower
    from qy.macroexpand import macroexpand_async
    from qy.register_vm import RegisterVirtualMachine

    expansion = await macroexpand_async(forms, runtime_env)
    program = lower(expansion.forms, runtime_env)
    diagnostics = (*expansion.diagnostics, *program.diagnostics)
    errors = tuple(item for item in diagnostics if item.severity == "error")
    if errors:
        if len(errors) == 1 and errors[0].message.startswith("unresolved symbol "):
            symbol = errors[0].message.removeprefix("unresolved symbol ").strip("'")
            span = SourceSpan(start_line=errors[0].line, start_column=errors[0].column)
            raise QyResolveError(
                errors[0].message,
                span=span,
                frames=(TraceFrame("call", None, span),),
                metadata={"symbol": symbol},
            )
        messages = "; ".join(item.message for item in errors)
        first = errors[0]
        raise QyRuntimeError(
            f"cannot evaluate program with diagnostics: {messages}",
            span=SourceSpan(start_line=first.line, start_column=first.column),
        )
    bytecode = compile_bytecode(program)
    bytecode_errors = tuple(item for item in bytecode.diagnostics if item.severity == "error")
    if bytecode_errors:
        messages = "; ".join(item.message for item in bytecode_errors)
        first = bytecode_errors[0]
        raise QyRuntimeError(
            f"cannot evaluate bytecode program with diagnostics: {messages}",
            span=SourceSpan(start_line=first.line, start_column=first.column),
        )
    return await RegisterVirtualMachine(bytecode, runtime_env).evaluate_program()


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
    if isinstance(operator_value, UserFunction):
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


async def _evaluate_tail_body_async(
    body: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    if not body:
        raise QyArityError("body must contain at least one expression")
    for expression in body[:-1]:
        await evaluate_async(expression, env)
    return await _evaluate_tail_expression_async(body[-1], env, function)


async def _evaluate_tail_expression_async(
    expression: object,
    env: Environment,
    function: UserFunction,
) -> object:
    if _is_self_tail_call(expression, function, env):
        assert isinstance(expression, tuple)
        return await _evaluate_values(
            tuple(expression[1:]),
            env,
            lambda arguments: _TailCall(function, arguments),
        )
    if isinstance(expression, tuple) and expression:
        operator = expression[0]
        args = tuple(expression[1:])
        if operator == Symbol("cond"):
            return await _evaluate_tail_cond_async(args, env, function)
        if operator == Symbol("let"):
            return await _evaluate_tail_let_async(args, env, function)
    return await evaluate_async(expression, env)


def _is_self_tail_call(expression: object, function: UserFunction, env: Environment) -> bool:
    if not isinstance(expression, tuple) or not expression:
        return False
    operator = expression[0]
    if not isinstance(operator, Symbol) or operator != function.name:
        return False
    try:
        return env.resolve(operator) is function
    except QyError:
        return False


async def _evaluate_tail_cond_async(
    args: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            raise QyTypeError(
                f"cond clause must be a pair, got {clause!r}",
                span=get_span(clause),
                metadata={"clause": clause},
            )
        condition, result = clause
        if _truthy(await evaluate_async(condition, env)):
            return await _evaluate_tail_expression_async(result, env, function)
    return None


async def _evaluate_tail_let_async(
    args: tuple[object, ...],
    env: Environment,
    function: UserFunction,
) -> object:
    if len(args) < 2:
        raise QyArityError("let expects bindings and at least one body expression")

    bindings, *body = args
    if not isinstance(bindings, tuple):
        raise QyTypeError(
            f"let bindings must be a list, got {bindings!r}",
            span=get_span(bindings),
        )

    local_env = env.child()
    for binding in bindings:
        if not isinstance(binding, tuple) or len(binding) != 2:
            raise QyTypeError(
                f"let binding must be a pair, got {binding!r}",
                span=get_span(binding),
            )
        name, value_expression = binding
        local_env.define(
            ensure_symbol(name, "let binding name"),
            await evaluate_async(value_expression, local_env),
        )

    return await _evaluate_tail_body_async(tuple(body), local_env, function)


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
