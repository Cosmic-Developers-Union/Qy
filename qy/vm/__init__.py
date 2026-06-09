# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Qy 虚拟机 Python 实现。.

目标：register VM 的完整 Python 实现。
当前：register VM 实现在 qy/vm/instance/machine.py。
禁止：不得定义 VM 规格（规格在 qy/backend/vm/spec/）。
"""

# Note: Do not import qy.vm.interp here to avoid circular imports.
# qy.vm.interp imports qy.vm.instance.machine, which imports qy.vm.bytecode.
# Importing qy.vm.bytecode triggers qy.vm.__init__, creating a cycle.

__all__ = []
