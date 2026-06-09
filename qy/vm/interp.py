# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 解释器入口。.

目标：提供 VM 执行的公共入口函数。
当前：从 qy/vm/instance/machine.py 重导出。
禁止：不得绕过 bytecode 直接解释 HIR/MIR。
"""

from qy.vm.instance.machine import RegisterVirtualMachine
from qy.vm.instance.machine import evaluate_bytecode
from qy.vm.instance.machine import evaluate_bytecode_async
from qy.vm.instance.machine import evaluate_bytecode_source
from qy.vm.instance.machine import evaluate_bytecode_source_async

__all__ = [
    "RegisterVirtualMachine",
    "evaluate_bytecode",
    "evaluate_bytecode_async",
    "evaluate_bytecode_source",
    "evaluate_bytecode_source_async",
]
