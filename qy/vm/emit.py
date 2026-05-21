# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 字节码发射。.

目标：从 LIR 发射 bytecode。
当前：从 qy/backend/vm/compiler.py 重导出。
禁止：不得重新理解 HIR/MIR 语义。
"""

from qy.backend.vm.compiler import compile_bytecode

__all__ = ["compile_bytecode"]
