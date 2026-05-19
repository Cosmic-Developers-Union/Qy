# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Python VM emit 兼容目标模块。.

目标：
- 迁移期只保留 Python VM implementation 需要的本地适配。
- 长期 bytecode emit 应归属 `qy/backend/vm/emit.py`，并遵守 `qy/backend/vm/spec`。

当前：
- 占位模块；真实实现仍在 `qy/bytecode_compiler.py`。

禁止：
- 不得重新理解 HIR/MIR 语义。
- 不得定义 VM target spec。
"""
