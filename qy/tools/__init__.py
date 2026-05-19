# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy 工具目标包。.

目标：
- 承载 check、fmt、lint、lsp、bench 等维护者与编辑器工具。
- 所有工具读取同一 Qy 实例事实，包括 pre-symbol-space-chain、profile、operator metadata。

当前：
- 占位包；实现仍主要位于 `analyzer.py`、`formatter.py`、`lsp.py`、`benchmark.py`。

禁止：
- 工具不得私造语言规则，也不得绕过 pipeline 直接猜测语义。
"""
