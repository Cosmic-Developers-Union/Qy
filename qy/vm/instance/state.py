# coding: utf-8
"""VM 实例执行状态。.

目标：表示一次 VM 执行的可变状态（pc、寄存器、作用域栈）。
当前：从 register_vm.py 的 _Frame 提取的目标结构。
禁止：不得定义 opcode 或 ABI 规格。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


@dataclass(slots=True)
class ExecutionState:
    """一次函数执行的可变状态。."""

    pc: int = 0
    registers: list[object] = field(default_factory=list)
    scope_stack: list[object] = field(default_factory=list)
    results: list[object] = field(default_factory=list)
