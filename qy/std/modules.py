# coding: utf-8
"""标准库 modules 模块 — re-export from qy.stdlib.modules。.

目标：
- 让 `from qy.std.modules` 可导入
- 最终取代 qy.stdlib.modules
"""

from __future__ import annotations

from qy.stdlib.modules import operators

__all__ = ["operators"]
