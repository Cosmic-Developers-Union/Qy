# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 后端字节码发射。.

目标：从 LIR 降低到 bytecode，写入 spec 数据结构。
当前：从 qy/bytecode_compiler.py 重导出。
禁止：不得重新理解 HIR/MIR 语义。
"""

from qy.bytecode_compiler import compile_bytecode

__all__ = ["compile_bytecode"]
