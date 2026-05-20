# coding: utf-8
"""标准库 imports 模块 — re-export from qy.stdlib。.

目标：
- 让 `from qy.std.imports` 可导入
- 最终取代 qy.stdlib
"""

from __future__ import annotations

from qy.stdlib import LANGUAGE_CORE_MODULES
from qy.stdlib import OPTIONAL_STDLIB_MODULES
from qy.stdlib import PRELUDE_MODULES
from qy.stdlib import STANDARD_PROFILE_MODULES
from qy.stdlib import load_module
from qy.stdlib import load_module_async
from qy.stdlib import module_names
from qy.stdlib import register_module
from qy.stdlib import register_module_loader
from qy.stdlib import standard_bindings
from qy.stdlib import standard_profile_bindings

# 从 qy.stdlib.imports 导入解析相关
from qy.stdlib.imports import ImportSpec
from qy.stdlib.imports import parse_from_import

__all__ = [
    "LANGUAGE_CORE_MODULES",
    "OPTIONAL_STDLIB_MODULES",
    "PRELUDE_MODULES",
    "STANDARD_PROFILE_MODULES",
    "ImportSpec",
    "load_module",
    "load_module_async",
    "module_names",
    "parse_from_import",
    "register_module",
    "register_module_loader",
    "standard_bindings",
    "standard_profile_bindings",
]
