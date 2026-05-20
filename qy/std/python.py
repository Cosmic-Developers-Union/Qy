# coding: utf-8
"""标准库 python 模块 — re-export from qy.stdlib.python。.

目标：
- 让 `from qy.std.python` 可导入
- 最终取代 qy.stdlib.python
"""

from __future__ import annotations

from qy.stdlib.python import operators

__all__ = ["operators"]
