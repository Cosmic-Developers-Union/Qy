# coding: utf-8
"""标准库 arithmetic 模块 — re-export from qy.stdlib.arithmetic。.

目标：
- 让 `from qy.std.arithmetic` 可导入
- 最终取代 qy.stdlib.arithmetic
"""

from __future__ import annotations

from qy.stdlib.arithmetic import operators

__all__ = ["operators"]
