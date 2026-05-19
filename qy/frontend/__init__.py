# coding: utf-8
"""Qy 前端目标包。.

目标：
- 承载 source -> raw AST -> surface dialect 阶段。
- 只负责读取源码、构造 raw AST、执行 default surface dialect。
- 不得提前创建 runtime value。

当前：
- 占位包；实际实现位于 `qy/reader.py`（待迁移）。
- raw AST 模型仍在从 Python tuple 向 symbol/chain 迁移中。

禁止：
- 不得依赖 register VM 或 runtime evaluation 路径。
- 不得把 Python 字符串/数字提前物化为 runtime value。
"""

from __future__ import annotations
