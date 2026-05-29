# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 后端：字节码目标与发射。.

目标：VM target 的规格定义与 bytecode 发射。
当前：包含 spec/ 子包、bytecode 定义、compiler 和 emit 模块。
禁止：
- 不得包含 VM 执行逻辑
- 不得暴露绕过 pipeline 的 ``compile_bytecode`` / ``compile_mir_bytecode``
  捷径——这两个旧入口已删除。完整的源到字节码编译走 ``qy.build.pipeline``。
"""

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram
from qy.backend.vm.bytecode import Instruction
from qy.backend.vm.bytecode import Opcode
from qy.backend.vm.bytecode import Register
from qy.backend.vm.bytecode import deserialize_bytecode
from qy.backend.vm.bytecode import dump_bytecode
from qy.backend.vm.bytecode import pretty_print_bytecode
from qy.backend.vm.bytecode import serialize_bytecode
from qy.backend.vm.compiler import compile_lir_bytecode

__all__ = [
    "BytecodeFunction",
    "BytecodeProgram",
    "Instruction",
    "Opcode",
    "Register",
    "compile_lir_bytecode",
    "deserialize_bytecode",
    "dump_bytecode",
    "pretty_print_bytecode",
    "serialize_bytecode",
]
