# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM stack 目标模块。.

目标：
- 承载 virtual stack、frame stack、handler stack 的运行时结构。
- 后续应拆入 `qy/vm/instance/frame.py` 与 `qy/vm/instance/state.py`。

当前：
- 占位模块；真实实现仍在 `qy/virtual_stack.py`。

禁止：
- 不得在这里定义 VM target spec；spec 属于 `qy/backend/vm/spec`。
"""
