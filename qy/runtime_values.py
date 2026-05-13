# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.errors import QyArityError
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.environment import Environment

__all__ = ["EffectDefinition", "HostObjectRef", "UserFunction"]


@dataclass(frozen=True, slots=True)
class EffectDefinition:
    name: Symbol
    resumable: bool = True
    doc: str = ""


@dataclass(frozen=True, slots=True, eq=False)
class HostObjectRef:
    value: object


@dataclass(frozen=True, slots=True)
class _TailCall:
    function: object
    args: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class UserFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def __call__(self, *args: object) -> object:
        from qy.evaluator import _evaluate_tail_body_async

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
        current_args = args
        while True:
            local_env = self.closure.child(dict(zip(self.params, current_args, strict=True)))
            result = await _evaluate_tail_body_async(self.body, local_env, self)
            if not isinstance(result, _TailCall) or result.function is not self:
                return result
            current_args = result.args
