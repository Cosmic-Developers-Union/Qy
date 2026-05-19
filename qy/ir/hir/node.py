# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""HIR 节点目标模块。.

目标：
- 放置 resolved binding、structured control、operator/effect/module facts 的节点。
- 与 HIR build/lowering 边界分离。

当前：
- 占位模块；真实实现仍在待迁移的 `qy/ir/hir.py`。

禁止：
- 不得放入 CFG、virtual register、bytecode offset。
"""
