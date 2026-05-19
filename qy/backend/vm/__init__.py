# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM backend target 目标包。.

目标：
- 放置 VM target spec、bytecode emit、验证与适配代码。
- 与 `qy/vm` 保持清晰分工：这里描述 target 和产物，`qy/vm` 是 Python VM 实现。

当前：
- 占位包；spec 已放入 `qy/backend/vm/spec/`。

禁止：
- 不得复制 register VM runtime 语义。
- 不得依赖 `qy/vm` 的可变 VM instance。
"""
