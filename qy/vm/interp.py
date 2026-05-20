# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 解释器入口。.

目标：提供 VM 执行的公共入口函数。
当前：从 qy/register_vm.py 重导出，迁移完成后实现独立解释器。
禁止：不得绕过 bytecode 直接解释 HIR/MIR。
"""

from qy.register_vm import RegisterVirtualMachine
from qy.register_vm import evaluate_bytecode
from qy.register_vm import evaluate_bytecode_async
from qy.register_vm import evaluate_bytecode_source
from qy.register_vm import evaluate_bytecode_source_async

__all__ = [
    "RegisterVirtualMachine",
    "evaluate_bytecode",
    "evaluate_bytecode_async",
    "evaluate_bytecode_source",
    "evaluate_bytecode_source_async",
]
