# coding: utf-8
"""Compile-time evaluator used only by macro expansion.

This evaluator intentionally does not compile macro bodies to bytecode and does
not instantiate the register VM.  It evaluates the small compile-time language
needed by macro definitions and dispatches already-registered pure/scope
operators through their public operator objects.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

from qy.core.operator_runtime import validate_operator_arity
from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import cons
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.frontend.reader import DottedTuple
from qy.frontend.reader import SourceSpan
from qy.frontend.reader import Symbol
from qy.frontend.reader import get_span
from qy.sem.core import T as QY_T
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.vm.instance.frame import QyContinuation

__all__ = ["evaluate_compile_time_body"]


async def evaluate_compile_time_body(body: tuple[object, ...], env: Environment) -> object:
    if not body:
        raise QyArityError("macro body must contain at least one expression")
    result: object = nil
    for form in body:
        result = await _eval_form(form, env)
    return result


async def _eval_form(form: object, env: Environment) -> object:
    if isinstance(form, Symbol):
        return env.resolve(form)
    if not _is_call_form(form):
        return form

    operator = _operator_of(form)
    args = _args_of(form)

    if operator == Symbol("quote"):
        _require_arity("quote", args, 1)
        return args[0]
    if operator == Symbol("quasiquote"):
        _require_arity("quasiquote", args, 1)
        return await _eval_quasiquote(args[0], env, depth=0)
    if operator == Symbol("let"):
        return await _eval_let(args, env)
    if operator == Symbol("cond"):
        return await _eval_cond(args, env)
    if operator == Symbol("define"):
        return await _eval_define(args, env)
    if operator == Symbol("assert"):
        return await _eval_assert(args, env, form)

    callee = await _eval_form(operator, env)
    return await _call_compile_time(callee, args, env, span=get_span(form))


async def _eval_let(args: tuple[object, ...], env: Environment) -> object:
    if len(args) < 2:
        raise QyArityError("let expects bindings and at least one body expression")
    bindings_form = args[0]
    local_env = env.child()
    for binding in _form_to_list(bindings_form):
        items = _form_to_list(binding)
        if len(items) != 2 or not isinstance(items[0], Symbol):
            raise QyTypeError(f"let binding must be (name value), got {binding!r}")
        local_env.define(items[0], await _eval_form(items[1], local_env))
    return await evaluate_compile_time_body(args[1:], local_env)


async def _eval_cond(args: tuple[object, ...], env: Environment) -> object:
    for clause in args:
        items = _form_to_list(clause)
        if len(items) != 2:
            raise QyTypeError(f"cond clause must be (condition expression), got {clause!r}")
        if _truthy(await _eval_form(items[0], env)):
            return await _eval_form(items[1], env)
    return nil


async def _eval_define(args: tuple[object, ...], env: Environment) -> object:
    if len(args) != 2 or not isinstance(args[0], Symbol):
        raise QyArityError("define expects a symbol and a value")
    value = await _eval_form(args[1], env)
    return env.define(args[0], value)


async def _eval_assert(args: tuple[object, ...], env: Environment, form: object) -> object:
    if len(args) not in {1, 2}:
        raise QyArityError("assert expects one or two arguments", span=get_span(form))
    if _truthy(await _eval_form(args[0], env)):
        return QY_T
    payload = await _eval_form(args[1], env) if len(args) == 2 else Symbol("assertion failed")
    raise QyEffectSignal(
        "assert-failed",
        payload,
        _identity_continuation("assert-failed", resumable=False),
        resumable=False,
        span=get_span(form),
    )


async def _call_compile_time(
    callee: object,
    raw_args: tuple[object, ...],
    env: Environment,
    *,
    span: SourceSpan | None,
) -> object:
    if isinstance(callee, EffectOperator):
        raise QyEffectSignal(
            callee.name,
            raw_args,
            _identity_continuation(callee.name, resumable=False),
            resumable=False,
            span=span,
        )
    if isinstance(callee, PureOperator):
        if callee.argument_evaluator is not None:
            processed = await _await_if_needed(callee.argument_evaluator(raw_args, env))
            if not isinstance(processed, tuple):
                raise QyTypeError(
                    f"custom argument evaluator for {callee.name} must return a tuple"
                )
            validate_operator_arity(callee, len(processed), span=span)
            return await _await_if_needed(callee.func(*processed))
        args = await _eval_args(raw_args, env)
        validate_operator_arity(callee, len(args), span=span)
        return await _await_if_needed(callee.func(*args))
    if isinstance(callee, ScopeOperator | ControlOperator | MetaOperator):
        validate_operator_arity(callee, len(raw_args), span=span)
        return await _await_if_needed(callee.func(raw_args, env))
    if callable(callee):
        args = await _eval_args(raw_args, env)
        host_callable = cast(Callable[..., object], callee)
        return await _await_if_needed(host_callable(*args))
    raise QyRuntimeError(f"compile-time call resolved to non-callable {callee!r}", span=span)


async def _eval_quasiquote(value: object, env: Environment, *, depth: int) -> object:
    if _is_call_form(value):
        operator = _operator_of(value)
        args = _args_of(value)
        if operator == Symbol("unquote"):
            _require_arity("unquote", args, 1)
            if depth == 0:
                return await _eval_form(args[0], env)
            return _rebuild_call(operator, (await _eval_quasiquote(args[0], env, depth=depth - 1),))
        if operator == Symbol("quasiquote"):
            _require_arity("quasiquote", args, 1)
            return _rebuild_call(operator, (await _eval_quasiquote(args[0], env, depth=depth + 1),))
    if is_chain(value):
        return await _eval_quasiquote_chain(value, env, depth=depth)
    if isinstance(value, tuple) and not isinstance(value, DottedTuple):
        items: list[object] = []
        for item in value:
            items.append(await _eval_quasiquote(item, env, depth=depth))
        return tuple(items)
    return value


async def _eval_args(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    values: list[object] = []
    for arg in args:
        values.append(await _eval_form(arg, env))
    return tuple(values)


async def _eval_quasiquote_chain(value: object, env: Environment, *, depth: int) -> object:
    items: list[object] = []
    current = value
    while is_chain(current):
        head = car(current)
        if _is_call_form(head) and _operator_of(head) == Symbol("unquote-splicing") and depth == 0:
            splice_args = _args_of(head)
            _require_arity("unquote-splicing", splice_args, 1)
            items.extend(_splice_items(await _eval_form(splice_args[0], env)))
        else:
            items.append(await _eval_quasiquote(head, env, depth=depth))
        current = cdr(current)
    if not is_nil(current):
        return _chain_from_items(items, await _eval_quasiquote(current, env, depth=depth))
    return list_to_chain(items)


def _splice_items(value: object) -> tuple[object, ...]:
    from qy.sem.core import ListValue
    from qy.sem.core import TupleValue

    if is_nil(value):
        return ()
    if is_chain(value):
        return tuple(chain_to_list(value))
    if isinstance(value, TupleValue | ListValue):
        return value.items
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise QyTypeError(f"unquote-splicing expects a sequence, got {value!r}")


def _chain_from_items(items: list[object], tail: object) -> object:
    result = tail
    for item in reversed(items):
        result = cons(item, result)
    return result


def _is_call_form(form: object) -> bool:
    if is_chain(form):
        return not is_nil(form)
    return isinstance(form, tuple) and not isinstance(form, DottedTuple) and len(form) > 0


def _operator_of(form: object) -> object:
    if is_chain(form):
        return car(form)
    if isinstance(form, tuple) and form:
        return form[0]
    raise QyTypeError(f"expected call form, got {form!r}")


def _args_of(form: object) -> tuple[object, ...]:
    if is_chain(form):
        rest = cdr(form)
        if is_nil(rest):
            return ()
        if is_chain(rest):
            return tuple(chain_to_list(rest))
        return (rest,)
    if isinstance(form, tuple) and form:
        return form[1:]
    return ()


def _form_to_list(form: object) -> list[object]:
    if is_nil(form):
        return []
    if is_chain(form):
        return chain_to_list(form)
    if isinstance(form, tuple):
        return list(form)
    raise QyTypeError(f"expected list form, got {form!r}")


def _rebuild_call(operator: object, args: tuple[object, ...]) -> object:
    return list_to_chain((operator, *args))


def _require_arity(name: str, args: tuple[object, ...], expected: int) -> None:
    if len(args) != expected:
        raise QyArityError(f"{name} expects exactly {expected} argument(s), got {len(args)}")


def _truthy(value: object) -> bool:
    return not is_nil(value)


def _identity_continuation(effect_name: str, *, resumable: bool) -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation(effect_name, resumable, resume)


async def _await_if_needed(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value
