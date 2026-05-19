# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy core node 目标模块。

目标：
- 放置 symbol、immutable chain、binding slot 等核心模型的数据结构。
- 为 frontend、macro、HIR lowering、VM 提供共享类型。

当前：
- 占位模块；实现仍分散在 legacy 文件中。

禁止：
- 不得放入 HIR/MIR/LIR 节点。
- 不得放入 standard profile 便利算子。
"""
