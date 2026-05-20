# coding: utf-8
"""VM state spec 目标模块。.

目标：
- 描述 VM target 抽象状态：program counter、register file、frame stack、handler stack、task state。
- 只描述规格，不保存某次执行的可变状态。

当前：
- 提供抽象的 VM 状态规格，描述 VM 必须维护的状态契约。
- 这些规格指导 VM 实现，但不包含具体的执行逻辑。

禁止：
- 不得包含具体的执行逻辑。
- 不得依赖某个 Python VM instance。
- 不得保存可变的执行状态（那些属于 VM 实现层）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "AbstractVMState",
    "FrameState",
    "VMState",
]


class VMState(Enum):
    """VM 执行状态枚举。.

    Attributes:
        READY: VM 已初始化，准备执行
        RUNNING: VM 正在执行
        SUSPENDED: VM 已挂起（等待效应处理）
        HALTED: VM 已停止（正常或异常终止）
    """

    READY = "ready"
    RUNNING = "running"
    SUSPENDED = "suspended"
    HALTED = "halted"


@dataclass(frozen=True, slots=True)
class AbstractVMState:
    """抽象 VM 状态契约。.

    描述任何 VM 实现必须维护的状态。

    Attributes:
        pc: 程序计数器（当前指令索引）
        register_count: 当前帧的寄存器数量
        scope_depth: 作用域栈深度
        handler_depth: 效应处理器栈深度
    """

    pc: int
    register_count: int
    scope_depth: int
    handler_depth: int


@dataclass(frozen=True, slots=True)
class FrameState:
    """抽象帧状态契约。.

    描述一个执行帧必须维护的状态。

    Attributes:
        function_index: 函数索引
        pc: 程序计数器
        register_count: 寄存器数量
        has_result_collector: 是否有结果收集器
    """

    function_index: int
    pc: int
    register_count: int
    has_result_collector: bool = False
