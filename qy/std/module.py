# coding: utf-8
"""标准库 module 模块 — re-export from qy.stdlib.module。.

目标：
- 让 `from qy.std.module` 可导入
- 最终取代 qy.stdlib.module
"""

from __future__ import annotations

from qy.stdlib.module import StandardModule

__all__ = ["StandardModule"]
