# coding: utf-8
"""标准库 effects 模块 — re-export from qy.stdlib.effects。.

目标：
- 让 `from qy.std.effects` 可导入
- 最终取代 qy.stdlib.effects
"""

from __future__ import annotations

from qy.stdlib.effects import legacy_operators
from qy.stdlib.effects import operators

__all__ = ["legacy_operators", "operators"]
