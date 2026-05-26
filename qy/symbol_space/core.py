# coding: utf-8
"""``qy.core`` 模块的聚合实现。.

数字算子 (``+ - * / = == < > <= >= mod``) 不在这里：它们的权威来源是
``number-ss``（见 ``qy/session/pre_ss.py::create_number_ss``）。用户脚本
可通过 ``(from qy.num import +)`` 显式引入；``qy.num`` 由
``qy.symbol_space._load_num_module`` 直接代理 ``number_ss_bindings()``。

本模块汇聚不属于 number-ss 的核心算子：chain / control / effect /
module。模块系统算子 (``from`` / ``module``) 来自
``qy.import_.operators``，因为它们桥接的是模块加载子系统。
"""

from __future__ import annotations

from qy.import_.module import StandardModule
from qy.import_.operators import operators as modules_operators
from qy.symbol_space.control import operators as control_operators
from qy.symbol_space.data import operators as chain_operators
from qy.symbol_space.data import python_container_operators
from qy.symbol_space.effects import operators as effects_operators


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
