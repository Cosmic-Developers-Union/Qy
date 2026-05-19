# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy Register VM 目标包。

目标：
- 承载 bytecode、bytecode emit、register VM interpreter、virtual stack、debug support。
- 成为唯一 runtime backend 的实现位置。

当前：
- 占位包；真实实现仍部分位于 `bytecode.py`、`bytecode_compiler.py`、`register_vm.py`、`virtual_stack.py`。

禁止：
- 不得重新引入 IR VM 或 evaluator backend。
- bytecode emit 不得重新解释 HIR/MIR 语义，只能消费 verified LIR。
"""
