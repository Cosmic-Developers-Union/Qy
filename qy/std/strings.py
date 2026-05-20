# coding: utf-8
"""标准库 strings 模块 — re-export from qy.stdlib.strings。.

目标：
- 让 `from qy.std.strings` 可导入
- 最终取代 qy.stdlib.strings
"""

from __future__ import annotations

from qy.stdlib.strings import module

__all__ = ["module"]
