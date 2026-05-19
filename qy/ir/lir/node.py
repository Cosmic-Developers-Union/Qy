# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""LIR 节点目标模块。.

目标：
- 放置 LIRProgram、LIRFunction、LIRInstruction、opcode 等节点定义。
- 与 frame/layout、verify、pretty 分离。

当前：
- 占位模块；真实实现仍在同名 package `__init__.py` 迁入前的旧文件中。

禁止：
- 不得放入 VM interpreter 或 bytecode encoder。
"""
