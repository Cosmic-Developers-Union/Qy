# coding: utf-8

from __future__ import annotations

from qy.bytecode import BytecodeFunctionValue
from qy.evaluator import ControlOperator
from qy.evaluator import EffectDefinition
from qy.evaluator import EffectOperator
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.evaluator import ScopeOperator
from qy.evaluator import UserFunction
from qy.macro import MacroDefinition
from qy.reader import Symbol
from qy.types import OperatorKind
from qy.types import TypeName
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyCons

__all__ = [
    "literal_type",
    "operator_kind_for_value",
    "value_type",
    "value_uses_eager_arguments",
]


def literal_type(value: object) -> TypeName:
    if value is QY_NIL:
        return "nil"
    if value is QY_T:
        return "T"
    if isinstance(value, QyCons):
        return "chain"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "none"
    if isinstance(value, Symbol):
        return "symbol"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, set):
        return "set"
    return "any"


def value_type(value: object) -> TypeName:
    if isinstance(
        value, PureOperator | ScopeOperator | ControlOperator | EffectOperator | MetaOperator
    ):
        return "operator"
    if isinstance(value, UserFunction | BytecodeFunctionValue):
        return "function"
    if isinstance(value, MacroDefinition):
        return "operator"
    if isinstance(value, EffectDefinition):
        return "effect"
    return literal_type(value)


def operator_kind_for_value(value: object) -> OperatorKind | None:
    if isinstance(value, PureOperator):
        return "pure"
    if isinstance(value, ScopeOperator):
        return "scope"
    if isinstance(value, ControlOperator):
        return "control"
    if isinstance(value, EffectOperator):
        return "effect"
    if isinstance(value, MetaOperator):
        return "meta"
    if isinstance(value, MacroDefinition):
        return "meta"
    return None


def value_uses_eager_arguments(value: object) -> bool:
    return isinstance(value, PureOperator) and value.argument_evaluator is None
