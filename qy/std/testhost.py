# coding: utf-8
"""标准库 testhost 模块 — re-export from qy.stdlib.testhost。.

目标：
- 让 `from qy.std.testhost` 可导入
- 最终取代 qy.stdlib.testhost
"""

from __future__ import annotations

from qy.stdlib.testhost import module
from qy.stdlib.testhost import set_cli_args

__all__ = ["module", "set_cli_args"]
