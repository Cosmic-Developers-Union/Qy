# coding: utf-8
"""VM 实例执行状态。.

目标：表示一次 VM 执行的可变状态（pc、寄存器、作用域栈）。
当前：从 register_vm.py 的 _Frame 提取的目标结构。
禁止：不得定义 opcode 或 ABI 规格。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field

from qy.errors import TraceFrame
from qy.vm.instance.frame import VirtualStackFrame

__all__ = [
    "ExecutionState",
    "VirtualStack",
]


@dataclass(slots=True)
class ExecutionState:
    """一次函数执行的可变状态。."""

    pc: int = 0
    registers: list[object] = field(default_factory=list)
    scope_stack: list[object] = field(default_factory=list)
    results: list[object] = field(default_factory=list)


class VirtualStack:
    """虚拟栈，用于错误追踪和调试。."""

    def __init__(self) -> None:
        self._frames: list[VirtualStackFrame] = []

    @contextmanager
    def frame(self, frame: VirtualStackFrame) -> Iterator[None]:
        self.push(frame)
        try:
            yield
        finally:
            self.pop()

    def push(self, frame: VirtualStackFrame) -> None:
        self._frames.append(frame)

    def replace_top(self, frame: VirtualStackFrame) -> None:
        if not self._frames:
            self.push(frame)
            return
        self._frames[-1] = frame

    def pop(self) -> None:
        if self._frames:
            self._frames.pop()

    def trace(self) -> tuple[TraceFrame, ...]:
        return tuple(frame.to_trace_frame() for frame in self._frames)
