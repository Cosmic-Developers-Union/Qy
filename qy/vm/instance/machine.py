# coding: utf-8
"""VM 实例：一次执行的入口。.

目标：定义 RegisterVirtualMachine 实例的公共接口。
当前：接口定义，实际执行仍在 qy/register_vm.py。
禁止：不得定义 opcode set 或 bytecode 格式。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from qy.vm.instance.state import ExecutionState


@dataclass(slots=True)
class VMInstance:
    """一次 VM 执行实例。."""

    program_index: int = 0
    state: ExecutionState = field(default_factory=ExecutionState)
    handler_stack: list[object] = field(default_factory=list)
    call_stack: list[object] = field(default_factory=list)
