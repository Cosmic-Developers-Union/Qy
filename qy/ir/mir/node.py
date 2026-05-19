# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""MIR 节点目标模块。

目标：
- 放置 CFG、basic block、virtual register、terminator、effect flow 节点。
- 与 MIR verifier / pretty printer 分离。

当前：
- 占位模块；真实实现仍在待迁移的 `qy/ir/mir.py`。

禁止：
- 不得放入物理布局、bytecode offset 或 VM frame 细节。
"""
