# coding: utf-8
"""Qy 标准扩展机制。.

Qy 语言内核（``qy.core`` / ``qy.frontend`` / ``qy.ir`` / ``qy.passes`` /
``qy.backend.vm.spec``）不得直接依赖宿主环境。宿主能力必须通过本包的
"扩展"边界进入语言：

- 一个扩展用 :class:`ExtensionDescriptor` 声明自己的名字、可导入模块名、
  所需宿主 capability，以及每个对外 binding 的 kind / signature；
- 扩展实现（宿主 Python 代码）通过工厂函数提供 ``StandardModule``；
- 模块系统按扩展声明的 ``module_name`` 装载，语言代码只看到普通 module，
  看不到宿主实现细节；
- 跨边界对象统一包装为 ``qy.sem.host.HostReference``，不得让宿主类型
  反向定义语言模型。

内置扩展见 ``qy.ext.python``（宿主 Python 执行）、``qy.ext.fs``（文件系统）、
``qy.ext.testhost``（测试/CLI 基础设施）。
"""

from __future__ import annotations

# 内置扩展在包导入时注册声明（模块内容仍按需装载）。
from qy.ext import fs as _fs  # noqa: F401
from qy.ext import interp as _interp  # noqa: F401
from qy.ext import python as _python  # noqa: F401
from qy.ext import python_module as _python_module  # noqa: F401
from qy.ext import testhost as _testhost  # noqa: F401
from qy.ext.descriptor import ExtensionBinding as ExtensionBinding
from qy.ext.descriptor import ExtensionCapability as ExtensionCapability
from qy.ext.descriptor import ExtensionDescriptor as ExtensionDescriptor
from qy.ext.registry import extension_descriptors as extension_descriptors
from qy.ext.registry import extension_names as extension_names
from qy.ext.registry import get_extension as get_extension
from qy.ext.registry import load_extension as load_extension
from qy.ext.registry import register_extension as register_extension

__all__ = [
    "ExtensionBinding",
    "ExtensionCapability",
    "ExtensionDescriptor",
    "extension_descriptors",
    "extension_names",
    "get_extension",
    "load_extension",
    "register_extension",
]
