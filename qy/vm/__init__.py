# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy Python VM implementation 目标包。

目标：
- 承载 Qy Register VM 的 Python 实现：instance、interpreter、runtime frame、state、scheduler、debug support。
- 实现 `qy/backend/vm/spec` 所定义的 VM target 规格。
- 成为当前唯一 runtime backend 的实现位置。

当前：
- 占位包；真实实现仍部分位于 `bytecode.py`、`bytecode_compiler.py`、`register_vm.py`、`virtual_stack.py`。

禁止：
- 不得重新引入 IR VM 或 evaluator backend。
- 不得在 Python VM implementation 中定义 opcode/ABI 规格；这些属于 `qy/backend/vm/spec`。
"""
