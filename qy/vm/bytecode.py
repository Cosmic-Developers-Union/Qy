# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 字节码类型桥接。.

目标：为 VM 实现层提供 bytecode 类型的便捷访问。
当前：从 qy/bytecode.py 重导出，迁移完成后改为从 spec 导入。
禁止：不得定义新的 bytecode 格式。
"""

from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeFunctionValue
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.bytecode import Opcode
from qy.bytecode import Register

__all__ = [
    "BytecodeFunction",
    "BytecodeFunctionValue",
    "BytecodeProgram",
    "Instruction",
    "Opcode",
    "Register",
]
