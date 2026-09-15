# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 字节码类型桥接。.

目标：为 VM 实现层提供 bytecode 类型的便捷访问。
当前：从 qy/backend/vm 导入规格类型，定义 BytecodeFunctionValue。
禁止：不得定义新的 bytecode 格式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import ClassVar

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram
from qy.backend.vm.bytecode import Instruction
from qy.backend.vm.bytecode import Opcode
from qy.backend.vm.bytecode import Register

if TYPE_CHECKING:
    from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = [
    "BytecodeFunction",
    "BytecodeFunctionValue",
    "BytecodeProgram",
    "Instruction",
    "Opcode",
    "Register",
]


@dataclass(frozen=True, slots=True)
class BytecodeFunctionValue:
    """Bytecode function with closure (Python VM implementation detail)."""

    # 语义类型标记：允许 qy.sem 在不 import qy.vm 的情况下识别可执行函数值。
    type_name: ClassVar[str] = "function"

    function: BytecodeFunction
    closure: Environment
    program: BytecodeProgram | None = None
