# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/core operator metadata schema

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Literal

from qy.types import TypeName

__all__ = [
    "CORE_OPERATOR_SIGNATURES",
    "STDLIB_OPERATOR_SIGNATURES",
    "ArgumentPolicy",
    "Arity",
    "EffectSpec",
    "OperatorSignature",
    "format_arity_message",
    "lookup_operator_signature",
]


ArgumentPolicy = Literal["eager", "raw", "body", "binding", "effect-name"]


@dataclass(frozen=True, slots=True)
class Arity:
    min: int = 0
    max: int | None = None

    def accepts(self, count: int) -> bool:
        if count < self.min:
            return False
        return self.max is None or count <= self.max


@dataclass(frozen=True, slots=True)
class EffectSpec:
    name: str
    resumable: bool | None = None


@dataclass(frozen=True, slots=True)
class OperatorSignature:
    return_type: TypeName
    arity: Arity = field(default_factory=Arity)
    argument_policy: tuple[ArgumentPolicy, ...] = ()
    argument_types: tuple[TypeName, ...] = ()
    rest_type: TypeName | None = None
    effects: tuple[EffectSpec, ...] = ()
    compile_time: bool = False
    runtime_meta: bool = False
    tail_transparent: bool = False


CORE_OPERATOR_SIGNATURES: dict[str, OperatorSignature] = {
    "all": OperatorSignature("any", Arity(), ("body",), tail_transparent=True),
    "apply": OperatorSignature("any", Arity(2, 2), ("eager", "eager"), tail_transparent=True),
    "atom": OperatorSignature("bool", Arity(1, 1)),
    "capture": OperatorSignature("any", Arity(1, 1), ("raw",), compile_time=True),
    "car": OperatorSignature("any", Arity(1, 1)),
    "cdr": OperatorSignature("any", Arity(1, 1)),
    "cond": OperatorSignature("any", Arity(), ("raw",), tail_transparent=True),
    "cons": OperatorSignature("chain", Arity(2, 2)),
    "define": OperatorSignature("any", Arity(2, 2), ("binding", "eager")),
    "defeffect": OperatorSignature("effect", Arity(1), ("binding", "raw")),
    "defun": OperatorSignature("function", Arity(3), ("binding", "raw", "body")),
    "eq": OperatorSignature("bool", Arity(2, 2)),
    "from": OperatorSignature("none", Arity(3), ("raw",)),
    "gensym": OperatorSignature("symbol", Arity(0, 1), ("raw",), compile_time=True),
    "handle": OperatorSignature("any", Arity(2, 2), ("raw", "raw"), tail_transparent=True),
    "lambda": OperatorSignature("function", Arity(2), ("raw", "body")),
    "let": OperatorSignature("any", Arity(2), ("raw", "body"), tail_transparent=True),
    "macro": OperatorSignature(
        "operator",
        Arity(3),
        ("binding", "raw", "body"),
        compile_time=True,
    ),
    "module": OperatorSignature("any", Arity(1), ("binding", "body")),
    "parallel": OperatorSignature("any", Arity(), ("body",), tail_transparent=True),
    "perform": OperatorSignature("any", Arity(2, 2), ("effect-name", "eager")),
    "pipeline": OperatorSignature("any", Arity(), ("body",), tail_transparent=True),
    "quasiquote": OperatorSignature("any", Arity(1, 1), ("raw",), compile_time=True),
    "quote": OperatorSignature("any", Arity(1, 1), ("raw",), compile_time=True),
    "race": OperatorSignature("any", Arity(), ("body",), tail_transparent=True),
    "resume": OperatorSignature("any", Arity(2, 2)),
    "unquote": OperatorSignature("any", Arity(1, 1), ("raw",), compile_time=True),
    "unquote-splicing": OperatorSignature("any", Arity(1, 1), ("raw",), compile_time=True),
}


STDLIB_OPERATOR_SIGNATURES: dict[str, OperatorSignature] = {
    "*": OperatorSignature("number", Arity(), rest_type="number"),
    "+": OperatorSignature("number", Arity(), rest_type="number"),
    "-": OperatorSignature("number", Arity(1), rest_type="number"),
    "/": OperatorSignature("number", Arity(1), rest_type="number"),
    "=": OperatorSignature("bool", Arity(2, 2)),
    "==": OperatorSignature("bool", Arity(2, 2)),
    "assert": OperatorSignature(
        "any",
        Arity(1, 2),
        effects=(EffectSpec("assert-failed", resumable=False),),
    ),
    "eval": OperatorSignature("any", Arity(1, 1), ("eager",), runtime_meta=True),
    "is": OperatorSignature("bool", Arity(2, 2)),
    "truthy": OperatorSignature("bool", Arity(1, 1)),
    "append": OperatorSignature("any", Arity(2, 2)),
}


def lookup_operator_signature(name: str) -> OperatorSignature | None:
    if (signature := CORE_OPERATOR_SIGNATURES.get(name)) is not None:
        return signature
    return STDLIB_OPERATOR_SIGNATURES.get(name)


def format_arity_message(name: str, signature: OperatorSignature, actual: int) -> str:
    if signature.arity.max is None:
        return f"{name} expects at least {signature.arity.min} arguments, got {actual}"
    if signature.arity.min == signature.arity.max:
        return f"{name} expects exactly {signature.arity.min} arguments, got {actual}"
    return (
        f"{name} expects between {signature.arity.min} and {signature.arity.max} "
        f"arguments, got {actual}"
    )
