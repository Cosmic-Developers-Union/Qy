# coding: utf-8
"""标准库 control 模块 — re-export from qy.stdlib.control。.

目标：
- 让 `from qy.std.control` 可导入
- 最终取代 qy.stdlib.control
"""

from __future__ import annotations

from qy.stdlib.control import legacy_operators
from qy.stdlib.control import operators

__all__ = ["legacy_operators", "operators"]
