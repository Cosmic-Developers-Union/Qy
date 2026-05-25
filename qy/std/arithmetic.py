# coding: utf-8
"""Arithmetic operators shim.

历史上 ``+ - * / =`` 等数字算子住在这里, 通过 stdlib profile 被拷贝进
pre-ssc 中名为 "stdlib" 的层。重构后, 这些算子的权威实现迁到了
``qy/session/number_ops.py`` —— 它们直接住在 number-ss 内部, 与数字字面量
并列。

本模块仅作为 thin re-export shim 存在, 保留以下兼容路径:

- ``operators()`` 仍存在, 但代理 ``number_ss_bindings()``。
- ``qy/std/__init__.py::_load_num_module`` 与 ``qy/std/core.py`` 通过此函数
  组装 ``qy.num`` / ``qy.core`` 模块。
- ``tests/test_stdlib_arithmetic.py`` 直接导入 ``_add / _sub / _mul / _div /
  _num_eq / _py_eq`` 私有 kernel; 这些名字保留, 转发到 ``number_ops``。

新代码不应 import 本模块; 改用 ``qy.session.number_ops``。
"""

from __future__ import annotations

from qy.frontend.reader import Symbol
from qy.session.number_ops import _add
from qy.session.number_ops import _div
from qy.session.number_ops import _mul
from qy.session.number_ops import _num_eq
from qy.session.number_ops import _py_eq
from qy.session.number_ops import _sub
from qy.session.number_ops import number_ss_bindings

__all__ = [
    "_add",
    "_div",
    "_mul",
    "_num_eq",
    "_py_eq",
    "_sub",
    "operators",
]


def operators() -> dict[Symbol, object]:
    """Return number-ss algebraic operator bindings (compatibility shim)."""
    return number_ss_bindings()
