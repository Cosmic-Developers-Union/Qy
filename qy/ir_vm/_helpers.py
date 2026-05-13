# coding: utf-8

from __future__ import annotations

import inspect

from qy.errors import QyRuntimeError
from qy.errors import SourceSpan
from qy.ir import CallExpr
from qy.ir import ProgramIR
from qy.ir import SymbolRefExpr
from qy.reader import DottedTuple
from qy.values import QY_NIL
from qy.values import list_to_qy_cons

__all__: list[str] = []


def _raise_for_diagnostics(program: ProgramIR) -> None:
    diagnostics = tuple(item for item in program.diagnostics if item.severity == "error")
    if not diagnostics:
        return
    messages = "; ".join(item.message for item in diagnostics)
    raise QyRuntimeError(f"cannot execute IR with diagnostics: {messages}")


def _quote_data(value: object) -> object:
    if isinstance(value, DottedTuple):
        return list_to_qy_cons((_quote_data(item) for item in value), _quote_data(value.tail))
    if isinstance(value, tuple):
        return list_to_qy_cons(_quote_data(item) for item in value)
    return value


def _truthy(value: object) -> bool:
    return value is not False and value is not None and value is not QY_NIL and value != ()


def _raw_operator_expression(expression: CallExpr) -> object:
    if isinstance(expression.operator, SymbolRefExpr):
        return expression.operator.symbol
    return expression.operator


def _function_stack_frame(function: object, span: SourceSpan | None) -> object:
    from qy.ir_vm._core import IRFunction
    from qy.virtual_stack import VirtualStackFrame

    assert isinstance(function, IRFunction)
    name = None if function.name.name == "<lambda>" else function.name.name
    kind = "lambda" if name is None else "call"
    return VirtualStackFrame(kind, name, span or function.name.span)


async def _await_if_needed(value: object) -> object:
    if inspect.iscoroutine(value):
        return await value
    return value


def _identity_continuation(effect_name: str, resumable: bool) -> object:
    from qy.continuation import QyContinuation

    async def resume(value: object) -> object:
        return value

    return QyContinuation(effect_name, resumable, resume)
