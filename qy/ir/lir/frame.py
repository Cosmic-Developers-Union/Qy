# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""LIR frame/layout 目标模块。

目标：
- 建模 virtual stack frame、continuation frame、handler frame、task frame。
- 建模 symbol-space-chain transition、binding slot layout、handler table layout。

当前：
- 占位模块。

禁止：
- 不得把 frame 语义留给 VM 临时 Python 对象隐式承担。
"""
