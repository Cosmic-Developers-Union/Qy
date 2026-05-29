# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy macro 系统。.

承载 macro definition、macro expansion、hygiene、trace、source map、compile-time symbol-space。

禁止：
- macro expand 不得长期依赖 register VM 作为普通 runtime 执行路径。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import cast

if TYPE_CHECKING:
    from qy.session.runtime_space import RuntimeSpace as Environment
from qy.errors import QyArityError
from qy.frontend.reader import Form
from qy.frontend.reader import Symbol

__all__ = [
    "CapturedForm",
    "MacroDefinition",
    "MacroEffectPolicy",
    "MacroExpansion",
    "MacroExpansionOptions",
    "MacroExpansionServices",
    "MacroExpansionTrace",
    "MacroRename",
    "MacroScope",
    "MacroSourceMapEntry",
]


@dataclass(frozen=True, slots=True)
class CapturedForm:
    value: object


@dataclass(frozen=True, slots=True)
class MacroExpansionServices:
    gensym: Callable[[object | None], Symbol]
    capture: Callable[[object], CapturedForm]


@dataclass(frozen=True, slots=True)
class MacroDefinition:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[object, ...]
    closure: Environment
    rest_param: Symbol | None = None  # 可变参数名称（&body 或点对语法）

    async def expand(
        self,
        args: tuple[object, ...],
        services: MacroExpansionServices | None = None,
    ) -> object:
        # 检查参数数量
        min_args = len(self.params)
        if self.rest_param is None:
            # 固定参数数量
            if len(args) != min_args:
                raise QyArityError(
                    f"{self.name.name} expects {min_args} arguments, got {len(args)}",
                    span=self.name.span,
                    metadata={
                        "expected": min_args,
                        "actual": len(args),
                        "macro": self.name.name,
                    },
                )
            bindings = dict(zip(self.params, args, strict=True))
        else:
            # 可变参数
            if len(args) < min_args:
                raise QyArityError(
                    f"{self.name.name} expects at least {min_args} arguments, got {len(args)}",
                    span=self.name.span,
                    metadata={
                        "expected": f"at least {min_args}",
                        "actual": len(args),
                        "macro": self.name.name,
                    },
                )
            # 绑定固定参数
            bindings = dict(zip(self.params, args[:min_args], strict=True))
            # 绑定剩余参数为列表
            from qy.core.syntax import list_to_chain

            rest_args = args[min_args:]
            bindings[self.rest_param] = list_to_chain(list(rest_args))

        local_env = self.closure.child(bindings)
        if services is not None:
            local_env.register_pure("gensym", services.gensym, doc="生成 hygienic macro symbol。")
            local_env.register_pure(
                "capture",
                services.capture,
                doc="显式保留调用点 symbol/form，跳过默认 hygiene rewrite。",
            )

        from qy.build.pipeline import bytecode_artifact
        from qy.build.pipeline import compile_core_forms_to_bytecode_async
        from qy.passes.pass_base import PipelineSession
        from qy.vm.instance.machine import RegisterVirtualMachine

        forms = list(cast(tuple[Form, ...], self.body))
        session = PipelineSession(env=local_env)
        result = await compile_core_forms_to_bytecode_async(forms, session)
        bytecode = bytecode_artifact(result)
        return await RegisterVirtualMachine(bytecode, local_env).evaluate()


from qy.macro.expand import MacroEffectPolicy as MacroEffectPolicy  # noqa: E402
from qy.macro.expand import MacroExpansion as MacroExpansion  # noqa: E402
from qy.macro.expand import MacroExpansionOptions as MacroExpansionOptions  # noqa: E402
from qy.macro.hygiene import MacroRename as MacroRename  # noqa: E402
from qy.macro.scope import MacroScope as MacroScope  # noqa: E402
from qy.macro.trace import MacroExpansionTrace as MacroExpansionTrace  # noqa: E402
from qy.macro.trace import MacroSourceMapEntry as MacroSourceMapEntry  # noqa: E402
