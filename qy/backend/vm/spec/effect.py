# coding: utf-8
"""VM effect/continuation spec 目标模块。.

目标：
- 定义 perform/handle/resume 在 VM target 层的低层协议。
- 规定 continuation frame、handler frame、multi-shot copy、ss-chain transition 的 VM 契约。

当前：
- 提供抽象的效应协议规格，描述效应处理、续延捕获、恢复的契约。
- 这些规格指导 LIR 降低和 VM 实现，但不包含具体的执行逻辑。

禁止：
- 不得包含具体的执行逻辑。
- 不得依赖某个 Python VM instance。
- 不得混入 runtime value 或具体的帧实现（那些属于 VM 实现层）。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ContinuationSpec",
    "EffectProtocol",
    "HandlerSpec",
]


@dataclass(frozen=True, slots=True)
class EffectProtocol:
    """VM 层效应协议规格。.

    描述一个效应在 VM 层的基本属性。

    Attributes:
        name: 效应名称
        resumable: 是否可恢复（当前总是 True）
    """

    name: str
    resumable: bool = True


@dataclass(frozen=True, slots=True)
class HandlerSpec:
    """效应处理器规格。.

    描述一个效应处理器在 VM 层的结构。

    Attributes:
        effect_name: 效应名称
        handler_function_index: 处理器函数索引
    """

    effect_name: str
    handler_function_index: int


@dataclass(frozen=True, slots=True)
class ContinuationSpec:
    """续延捕获规格。.

    描述效应恢复时必须捕获的状态。

    Attributes:
        registers: 是否捕获寄存器（当前总是 True）
        pc: 是否捕获程序计数器（当前总是 True）
        scope_stack: 是否捕获作用域栈（当前总是 True）
        result_collector: 是否捕获结果收集器（当前总是 True）
    """

    registers: bool = True
    pc: bool = True
    scope_stack: bool = True
    result_collector: bool = True
