# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from qy.compile_time import CompileTimeEnvironment
from qy.errors import QyArityError
from qy.reader import Form
from qy.reader import Symbol

__all__ = ["MacroDefinition", "MacroExpansionServices"]


@dataclass(frozen=True, slots=True)
class MacroExpansionServices:
    gensym: Callable[[object | None], Symbol]


@dataclass(frozen=True, slots=True)
class MacroDefinition:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: CompileTimeEnvironment

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
        local_env = self.closure.child(dict(zip(self.params, args, strict=True)))
        if services is not None:
            local_env.register_pure("gensym", services.gensym, doc="生成 hygienic macro symbol。")

        from qy.ir_vm import evaluate_ir_async
        from qy.lowering import lower

        return await evaluate_ir_async(
            lower(list(cast(tuple[Form, ...], self.body)), local_env), local_env
        )
