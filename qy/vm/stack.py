# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""VM 虚拟栈。.

目标：提供 VM 执行的虚拟调用栈。
当前：从 qy/virtual_stack.py 重导出。
禁止：不得混入语言语义。
"""

from qy.virtual_stack import VirtualStack
from qy.virtual_stack import VirtualStackFrame

__all__ = ["VirtualStack", "VirtualStackFrame"]
