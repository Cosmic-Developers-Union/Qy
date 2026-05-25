# coding: utf-8
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.analysis.scope import Scope
    from qy.core import OperatorKind
    from qy.core import TypeName
    from qy.core.operator_signature import OperatorSignature
    from qy.environment import Environment
    from qy.frontend.reader import Symbol

from qy.core.operator_signature import format_arity_message
from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.syntax import Chain
from qy.core.syntax import nil
from qy.diag import Diagnostic
from qy.errors import EvaluationError
from qy.macro import MacroDefinition
from qy.sem.core import T
from qy.sem.runtime import EffectDefinition
from qy.sem.runtime import UserFunction
from qy.session.pre_ss import default_literal_type


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
    if isinstance(value, UserFunction):
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


def value_signature(value: object) -> OperatorSignature | None:
    return getattr(value, "signature", None)


def operator_kind(operator: Symbol, env: Environment, scope: Scope) -> OperatorKind | None:
    if (binding := scope.lookup(operator)) is not None:
        return binding.operator_kind
    try:
        return operator_kind_for_value(env.resolve(operator))
    except EvaluationError:
        return None


def operator_uses_eager_arguments(operator: Symbol, env: Environment, scope: Scope) -> bool:
    if (binding := scope.lookup(operator)) is not None:
        return binding.operator_kind == "pure" and binding.eager_arguments
    try:
        return value_uses_eager_arguments(env.resolve(operator))
    except EvaluationError:
        return False


def operator_signature(
    operator: Symbol, env: Environment, scope: Scope
) -> OperatorSignature | None:
    if (binding := scope.lookup(operator)) is not None:
        return binding.signature
    try:
        return value_signature(env.resolve(operator))
    except EvaluationError:
        return None


def infer_symbol(
    symbol: Symbol,
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    literal_name = default_literal_type(symbol)
    if literal_name is not None:
        return literal_name
    if (binding := scope.lookup(symbol)) is not None:
        return binding.type_name
    try:
        return value_type(env.resolve(symbol))
    except EvaluationError:
        diagnostics.append(Diagnostic(f"unresolved symbol {symbol.name!r}"))
        return "unknown"


def signature_argument_is_eager(sig: OperatorSignature, index: int) -> bool:
    try:
        policy = sig.argument_policy[index]
    except IndexError:
        policy = "eager"
    return policy == "eager"


def signature_argument_type(sig: OperatorSignature, index: int) -> TypeName | None:
    try:
        return sig.argument_types[index]
    except IndexError:
        return sig.rest_type


def arity_message(name: str, sig: OperatorSignature, actual: int) -> str:
    return format_arity_message(name, sig, actual)


def effect_is_declared(effect: Symbol, env: Environment, scope: Scope) -> bool:
    if (binding := scope.lookup(effect)) is not None:
        return binding.type_name == "effect"
    try:
        return isinstance(env.resolve(effect), EffectDefinition)
    except EvaluationError:
        return False
