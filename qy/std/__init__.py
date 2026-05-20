# coding: utf-8
"""标准库：standard profile 与标准库目标包。.

目标：
- 提供 standard profile 与标准库实现
- 包含常用算子（+、-、*、/ 等）和标准函数
- 定义默认的 pre-symbol-space-chain

当前：
- 各子模块从 qy.stdlib.* re-export，迁移期兼容
- 新增长期标准能力应进入此包

禁止：
- 不是 Python helper 的随机集合
- 不得将 profile 便利算子提升为核心 form
- 不得绕过 symbol-space-chain 机制
"""

from __future__ import annotations

# 模块加载与管理（从 qy.stdlib.imports re-export）
from qy.std.imports import LANGUAGE_CORE_MODULES
from qy.std.imports import OPTIONAL_STDLIB_MODULES
from qy.std.imports import PRELUDE_MODULES
from qy.std.imports import STANDARD_PROFILE_MODULES
from qy.std.imports import load_module
from qy.std.imports import load_module_async
from qy.std.imports import module_names
from qy.std.imports import register_module
from qy.std.imports import register_module_loader
from qy.std.imports import standard_bindings
from qy.std.imports import standard_profile_bindings

# Module 数据类型
from qy.std.module import StandardModule

__all__ = [
    "LANGUAGE_CORE_MODULES",
    "OPTIONAL_STDLIB_MODULES",
    "PRELUDE_MODULES",
    "STANDARD_PROFILE_MODULES",
    "StandardModule",
    "load_module",
    "load_module_async",
    "module_names",
    "register_module",
    "register_module_loader",
    "standard_bindings",
    "standard_profile_bindings",
]
