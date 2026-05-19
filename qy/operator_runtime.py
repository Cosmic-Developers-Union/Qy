# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/core operator runtime schema

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.errors import QyArityError
from qy.errors import SourceSpan
from qy.macro import MacroDefinition
from qy.operator_signature import OperatorSignature
from qy.operator_signature import format_arity_message
from qy.operators import ControlOperator
from qy.operators import EffectOperator
from qy.operators import MetaOperator
from qy.operators import PureOperator
from qy.operators import ScopeOperator

__all__ = [
    "RuntimeArgumentMode",
    "RuntimeDispatchKind",
    "RuntimeOperatorSemantics",
    "operator_uses_raw_args",
    "runtime_operator_semantics",
    "validate_operator_arity",
]

RuntimeArgumentMode = Literal["eager", "raw", "custom"]
RuntimeDispatchKind = Literal["pure", "scope", "control", "effect", "meta", "macro", "unknown"]


@dataclass(frozen=True, slots=True)
class RuntimeOperatorSemantics:
    dispatch_kind: RuntimeDispatchKind
    argument_mode: RuntimeArgumentMode
    signature: OperatorSignature | None = None
    compile_time: bool = False
    runtime_meta: bool = False


def runtime_operator_semantics(operator: object) -> RuntimeOperatorSemantics:
    signature = _operator_signature(operator)
    compile_time = bool(signature and signature.compile_time)
    runtime_meta = bool(signature and signature.runtime_meta)
    if isinstance(operator, PureOperator):
        mode: RuntimeArgumentMode = "custom" if operator.argument_evaluator is not None else "eager"
        return RuntimeOperatorSemantics("pure", mode, signature, compile_time, runtime_meta)
    if isinstance(operator, ScopeOperator):
        return RuntimeOperatorSemantics("scope", "raw", signature, compile_time, runtime_meta)
    if isinstance(operator, ControlOperator):
        return RuntimeOperatorSemantics("control", "raw", signature, compile_time, runtime_meta)
    if isinstance(operator, EffectOperator):
        return RuntimeOperatorSemantics("effect", "raw", signature, compile_time, runtime_meta)
    if isinstance(operator, MetaOperator):
        return RuntimeOperatorSemantics("meta", "raw", signature, compile_time, True)
    if isinstance(operator, MacroDefinition):
        return RuntimeOperatorSemantics("macro", "raw", signature, True, True)
    return RuntimeOperatorSemantics("unknown", "eager", signature, compile_time, runtime_meta)


def operator_uses_raw_args(operator: object) -> bool:
    return runtime_operator_semantics(operator).argument_mode != "eager"


def validate_operator_arity(
    operator: object,
    actual: int,
    *,
    span: SourceSpan | None = None,
) -> None:
    semantics = runtime_operator_semantics(operator)
    signature = semantics.signature
    if signature is None or signature.arity.accepts(actual):
        return
    name = _operator_name(operator)
    raise QyArityError(
        format_arity_message(name, signature, actual),
        span=span,
        metadata={"operator": name, "expected": signature.arity, "actual": actual},
    )


def _operator_signature(operator: object) -> OperatorSignature | None:
    return getattr(operator, "signature", None)


def _operator_name(operator: object) -> str:
    name = getattr(operator, "name", None)
    if isinstance(name, str):
        return name
    return "call"
