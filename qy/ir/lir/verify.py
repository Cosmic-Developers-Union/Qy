# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""LIR verifier 目标模块。.

目标：
- 校验 LIR control、register、frame、handler、slot、debug metadata 的一致性。
- 成为 LIR -> bytecode / LLVM 之前的结构门。

当前：
- 占位模块。

禁止：
- verifier 不得重写程序；rewrite 应属于 passes。
"""
