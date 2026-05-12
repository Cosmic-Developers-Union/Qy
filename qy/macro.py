# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.errors import QyArityError
from qy.reader import Symbol

if TYPE_CHECKING:
    from qy.evaluator import Environment

__all__ = ["MacroDefinition", "MacroExpansionServices"]


@dataclass(frozen=True, slots=True)
class MacroExpansionServices:
    gensym: Callable[[object | None], Symbol]


@dataclass(frozen=True, slots=True)
class MacroDefinition:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment

    async def expand(
        self,
        args: tuple[object, ...],
        services: MacroExpansionServices | None = None,
    ) -> object:
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
        if services is not None:
            from qy.evaluator import PureOperator

            local_env.define(
                Symbol("gensym"),
                PureOperator("gensym", services.gensym, "生成 hygienic macro symbol。"),
            )
        return await evaluate_body_async(self.body, local_env)
