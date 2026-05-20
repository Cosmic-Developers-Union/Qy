# coding: utf-8
"""VM ABI spec 目标模块。.

目标：
- 定义 call ABI、register ABI、frame ABI、handler/continuation ABI、host adapter ABI。

当前：
- 提供抽象的 ABI 规格，描述调用约定、帧布局、寄存器分配策略。
- 这些规格指导 LIR 降低和 VM 实现，但不包含具体的执行逻辑。

禁止：
- 不得包含具体的执行逻辑。
- 不得依赖某个 Python VM instance。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CallConvention",
    "FrameLayout",
    "RegisterAllocation",
]


@dataclass(frozen=True, slots=True)
class CallConvention:
    """调用约定规格。.

    描述函数调用时参数如何传递、返回值如何处理、闭包如何捕获。

    Attributes:
        params_in_registers: 参数是否通过寄存器传递（当前总是 True）
        closure_captured: 是否支持闭包捕获（当前总是 True）
        tail_call_eligible: 是否支持尾调用优化（当前总是 True）
    """

    params_in_registers: bool = True
    closure_captured: bool = True
    tail_call_eligible: bool = True


@dataclass(frozen=True, slots=True)
class FrameLayout:
    """抽象帧布局规格。.

    描述一个 bytecode 函数执行时的帧结构。

    Attributes:
        register_count: 寄存器数量
        has_scope_stack: 是否有作用域栈（当前总是 True）
        has_result_collector: 是否有结果收集器（用于 all-gather 等操作）
    """

    register_count: int
    has_scope_stack: bool = True
    has_result_collector: bool = False


@dataclass(frozen=True, slots=True)
class RegisterAllocation:
    """寄存器分配策略规格。.

    描述寄存器如何分配给参数、局部变量、临时值。

    Attributes:
        param_start: 参数寄存器起始索引（通常为 0）
        param_count: 参数数量
        local_start: 局部变量寄存器起始索引
        temp_start: 临时寄存器起始索引
        total_count: 总寄存器数量
    """

    param_start: int
    param_count: int
    local_start: int
    temp_start: int
    total_count: int
