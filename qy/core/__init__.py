# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy 语言核心模型目标包。

目标：
- 保存 symbol、immutable chain、binding slot、operator/effect declaration 等核心语义模型。
- 为 reader、macro、HIR lowering、analyzer、VM 提供同一份核心事实。

当前：
- 占位包；大量实现仍散落在 `reader.py`、`environment.py`、`operators.py`、`values.py`。

禁止：
- 不得混入 standard profile 便利算子。
- 不得把 Python runtime value 当作 Qy 语言核心模型。
"""
