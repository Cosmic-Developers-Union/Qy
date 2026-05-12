# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.errors import QyArityError
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.evaluator import Environment

__all__ = ["MacroDefinition"]


@dataclass(frozen=True, slots=True)
class MacroDefinition:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def expand(self, args: tuple[object, ...]) -> object:
        if len(args) != len(self.params):
            raise QyArityError(
                f"{self.name.name} expects {len(self.params)} arguments, got {len(args)}",
                span=self.name.span,
                metadata={
                    "expected": len(self.params),
                    "actual": len(args),
                    "macro": self.name.name,
                },
            )
        from qy.evaluator import evaluate_body_async

        local_env = self.closure.child(dict(zip(self.params, args, strict=True)))
        return await evaluate_body_async(self.body, local_env)
