# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM backend emit 目标模块。

目标：
- 将 verified LIR 编码为符合 `qy/backend/vm/spec` 的 VM bytecode。
- 替代迁移期 `qy/bytecode_compiler.py`。

当前：
- 占位模块。

禁止：
- 不得重新理解 HIR/MIR 语义。
- 不得依赖 `qy/vm` 的 Python VM instance。
"""
