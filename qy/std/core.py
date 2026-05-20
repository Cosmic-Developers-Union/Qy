# coding: utf-8
"""标准库 core 模块 — re-export from qy.stdlib.core。.

目标：
- 让 `from qy.std.core` 可导入
- 最终取代 qy.stdlib.core
"""

from __future__ import annotations

from qy.stdlib.core import module

__all__ = ["module"]
