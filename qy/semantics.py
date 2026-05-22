# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/core + qy/sem semantic model

from __future__ import annotations

from typing import TYPE_CHECKING

from qy.core import OperatorKind
from qy.core import TypeName
from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.syntax import Chain
from qy.core.syntax import nil
from qy.frontend.reader import Symbol
from qy.macro import MacroDefinition
from qy.sem.core import T
from qy.sem.runtime import EffectDefinition
from qy.sem.runtime import UserFunction

if TYPE_CHECKING:
    pass

__all__ = [
    "literal_type",
    "operator_kind_for_value",
    "value_type",
    "value_uses_eager_arguments",
]


def literal_type(value: object) -> TypeName:
    if value is nil:
        return "nil"
    if value is T:
        return "T"
    if isinstance(value, Chain):
        return "chain"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "none"
    if isinstance(value, str):
        return "string"
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
    from qy.vm.bytecode import BytecodeFunctionValue

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
