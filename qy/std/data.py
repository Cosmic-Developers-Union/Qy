# coding: utf-8
"""标准库 data 模块 — re-export from qy.stdlib.data。.

目标：
- 让 `from qy.std.data` 可导入
- 最终取代 qy.stdlib.data
"""

from __future__ import annotations

from qy.stdlib.data import operators
from qy.stdlib.data import python_container_operators

__all__ = ["operators", "python_container_operators"]
