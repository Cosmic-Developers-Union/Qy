# coding: utf-8
"""``qy.core`` standard module.

不再持有数字算子 (``+ - * / = == < > <= >= mod``):

- 数字算子的权威来源是 ``number-ss`` (见
  ``qy/session/pre_ss.py::create_number_ss``)。
- 用户脚本仍可通过 ``(from qy.num import +)`` 显式引入; ``qy.num`` 模块的
  bindings 由 ``qy/std/__init__.py::_load_num_module`` 直接代理
  ``number_ss_bindings()``。

本模块只汇聚不属于 number-ss 的核心算子: chain / control / effect / module。
"""

from __future__ import annotations

from qy.std.control import operators as control_operators
from qy.std.data import operators as chain_operators
from qy.std.data import python_container_operators
from qy.std.effects import operators as effects_operators
from qy.std.module import StandardModule
from qy.std.modules import operators as modules_operators


def module() -> StandardModule:
    return StandardModule(
        "qy.core",
        {
            **chain_operators(),
            **python_container_operators(),
            **control_operators(),
            **effects_operators(),
            **modules_operators(),
        },
    )
