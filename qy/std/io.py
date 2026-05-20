# coding: utf-8
"""标准库 io 模块 — re-export from qy.stdlib.io。.

目标：
- 让 `from qy.std.io` 可导入
- 最终取代 qy.stdlib.io
"""

from __future__ import annotations

from qy.stdlib.io import module

__all__ = ["module"]
