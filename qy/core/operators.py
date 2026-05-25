# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Literal

if TYPE_CHECKING:
    from qy.core.operator_signature import OperatorSignature
    from qy.environment import Environment

OperatorKind = Literal["pure", "scope", "control", "effect", "meta"]

__all__ = [
    "ArgumentEvaluator",
    "ControlOperator",
    "EffectOperator",
    "EvaluationOperator",
    "MetaOperator",
    "PureOperator",
    "ScopeOperator",
    "SyntaxOperator",
    "value_uses_eager_arguments",
]

ArgumentEvaluator = Callable[[tuple[object, ...], "Environment"], object]


@dataclass(frozen=True, slots=True)
class PureOperator:
    name: str
    func: Callable[..., object]
    doc: str = ""
    argument_evaluator: ArgumentEvaluator | None = None
    signature: OperatorSignature | None = None

    @property
    def kind(self) -> OperatorKind:
        return "pure"

    def __post_init__(self) -> None:
        _set_default_signature(self)

    def __call__(self, *args: object) -> object:
        return self.func(*args)


@dataclass(frozen=True, slots=True)
class ScopeOperator:
    name: str
    func: Callable[..., object]
    doc: str = ""
    signature: OperatorSignature | None = None

    @property
    def kind(self) -> OperatorKind:
        return "scope"

    def __post_init__(self) -> None:
        _set_default_signature(self)

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class ControlOperator:
    name: str
    func: Callable[..., object]
    doc: str = ""
    signature: OperatorSignature | None = None

    @property
    def kind(self) -> OperatorKind:
        return "control"

    def __post_init__(self) -> None:
        _set_default_signature(self)

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class EffectOperator:
    name: str
    func: Callable[..., object]
    doc: str = ""
    signature: OperatorSignature | None = None

    @property
    def kind(self) -> OperatorKind:
        return "effect"

    def __post_init__(self) -> None:
        _set_default_signature(self)

    def __call__(self, args: tuple[object, ...], env: Environment) -> object:
        return self.func(args, env)


@dataclass(frozen=True, slots=True)
class MetaOperator:
    name: str
    func: Callable[..., object]
    doc: str = ""
    signature: OperatorSignature | None = None

    @property
    def kind(self) -> OperatorKind:
        return "meta"

    def __post_init__(self) -> None:
        _set_default_signature(self)

    def __call__(self, expression: tuple[object, ...], env: Environment) -> object:
        return self.func(expression, env)


EvaluationOperator = ControlOperator
SyntaxOperator = MetaOperator


def value_uses_eager_arguments(value: object) -> bool:
    return isinstance(value, PureOperator) and value.argument_evaluator is None


def _set_default_signature(operator: object) -> None:
    from typing import Any
    from typing import cast

    from qy.core.operator_signature import lookup_operator_signature

    signature = getattr(operator, "signature", None)
    if signature is None:
        name = cast(Any, operator).name
        object.__setattr__(
            operator,
            "signature",
            lookup_operator_signature(name),
        )
