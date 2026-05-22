# coding: utf-8
"""VM 实例帧结构。.

目标：定义函数帧、continuation 帧、handler 帧的运行时对象。
当前：从 register_vm.py 的 _Frame/_EffectFrame 提取。
禁止：不得包含 opcode dispatch 逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.errors import SourceSpan
from qy.errors import TraceFrame

__all__ = [
    "CapturedFrame",
    "FunctionFrame",
    "VirtualStackFrame",
]


@dataclass(slots=True)
class FunctionFrame:
    """活跃函数调用帧。."""

    function_index: int
    pc: int
    registers: list[object]
    scope_depth: int = 0


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """Effect continuation 捕获的帧快照。."""

    registers: tuple[object, ...]
    pc: int
    scope_depth: int
    results: tuple[object, ...]
    function_index: int


@dataclass(frozen=True, slots=True)
class VirtualStackFrame:
    """虚拟栈帧，用于错误追踪和调试。."""

    kind: str
    name: str | None = None
    span: SourceSpan | None = None

    def to_trace_frame(self) -> TraceFrame:
        return TraceFrame(self.kind, self.name, self.span)
