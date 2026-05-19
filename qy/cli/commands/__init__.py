# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy CLI 命令模块集合。

目标：
- 每个文件只负责一个命令或一组紧密相关命令。
- 命令实现读取 public API，不直接跨层调用内部 lowering 细节。

当前：
- 占位包；迁移期间可能与 `qy/cli.py` 并存。

禁止：
- 不得在命令模块里修补 reader、macro、IR、VM 语义。
"""
