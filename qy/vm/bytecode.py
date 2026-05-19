# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Python VM bytecode 兼容目标模块。

目标：
- 迁移期为 Python VM implementation 提供本地 bytecode 适配。
- 长期 BytecodeProgram、Instruction、opcode 规格归属 `qy/backend/vm/spec/bytecode.py`。

当前：
- 占位模块；真实实现仍在 `qy/bytecode.py`。

禁止：
- 不得重新理解 HIR/MIR 语义。
- 不得定义 VM target bytecode 规格。
"""
