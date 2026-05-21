# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 字节码类型桥接。.

目标：为 VM 实现层提供 bytecode 类型的便捷访问。
当前：从 qy/backend/vm 导入规格类型，从 qy/bytecode 导入 runtime value。
禁止：不得定义新的 bytecode 格式。
"""

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram
from qy.backend.vm.bytecode import Instruction
from qy.backend.vm.bytecode import Opcode
from qy.backend.vm.bytecode import Register
from qy.bytecode import BytecodeFunctionValue

__all__ = [
    "BytecodeFunction",
    "BytecodeFunctionValue",
    "BytecodeProgram",
    "Instruction",
    "Opcode",
    "Register",
]
