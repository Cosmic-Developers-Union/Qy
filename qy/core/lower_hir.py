# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""core -> HIR 边界辅助目标模块。.

目标：
- 放置从核心语义事实进入 HIR lowering 时需要的共享结构。
- 只描述 HIR lowering 前的核心 facts，不执行完整 lowering。

当前：
- 占位模块；实际 HIR lowering 仍在 `qy/passes/lower_hir.py` 和 legacy `qy/lowering.py`。

禁止：
- 不得成为第二套 lowering pass。
"""
