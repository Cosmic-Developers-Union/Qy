# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy macro 系统目标包。.

目标：
- 承载 macro definition、macro expansion、hygiene、trace、source map、compile-time symbol-space。
- 将 `qy/macro.py`、`macroexpand.py`、`macro_hygiene.py`、`macro_scope.py`、`macro_trace.py` 收口到同一包边界。

当前：
- 先迁入 `qy/macro.py` 的 public 类型，避免 package 遮蔽旧模块后破坏导入。
- `qy/macro.py` 仍是待删除的 legacy 同名文件。

禁止：
- macro expand 不得长期依赖 register VM 作为普通 runtime 执行路径。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from qy.compile_time import CompileTimeEnvironment
from qy.errors import QyArityError
from qy.reader import Form
from qy.reader import Symbol

__all__ = ["CapturedForm", "MacroDefinition", "MacroExpansionServices"]


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
    closure: CompileTimeEnvironment
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

        from qy.backend.vm.compiler import compile_bytecode
        from qy.passes.lower_hir import lower
        from qy.register_vm import RegisterVirtualMachine

        program = lower(list(cast(tuple[Form, ...], self.body)), local_env)
        bytecode = compile_bytecode(program)
        return await RegisterVirtualMachine(bytecode, local_env).evaluate()
