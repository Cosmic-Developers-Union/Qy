# coding: utf-8
"""const_fold 的算子来源边界测试。.

编译期求值只能使用**语言实现自身**的纯算子；宿主通过 ``register_pure`` 注入的
函数不得在编译期执行——那是可观察副作用（宿主可能在不同进程/时刻编译，AOT 更会
把宿主状态烘进产物），宿主函数还可能返回 coroutine 等非 Qy 值对象。
"""

from __future__ import annotations

import asyncio

from qy.core.syntax import Symbol
from qy.passes.optimize.const_fold import _collect_pure_ops
from qy.session.runtime_space import RuntimeSpace
from qy.session.runtime_space import create_standard_runtime_space


def test_language_implementation_operators_are_foldable():
    ops = _collect_pure_ops(create_standard_runtime_space())

    assert "+" in ops
    assert "*" in ops


def test_host_registered_pure_operator_is_not_foldable():
    env = create_standard_runtime_space()
    calls: list[int] = []

    def counted(value: object) -> object:
        calls.append(1)
        return value

    from qy.core.operators import PureOperator

    env.define(Symbol("counted"), PureOperator("counted", counted, "宿主计数函数。"))

    ops = _collect_pure_ops(env)

    assert "counted" not in ops
    assert calls == []


def test_host_registered_coroutine_operator_is_not_folded():
    """回归：宿主 async 算子曾被折成 coroutine 常量。."""
    env = create_standard_runtime_space()

    async def delayed(value: object) -> object:
        await asyncio.sleep(0)
        return value

    from qy.core.operators import PureOperator

    env.define(Symbol("delayed"), PureOperator("delayed", delayed, "宿主协程函数。"))
    ops = _collect_pure_ops(env)

    assert "delayed" not in ops


def test_collect_pure_ops_ignores_environment_override_with_host_function():
    """宿主用同名函数覆盖内建算子时，该名字不得再被折叠。."""
    env = RuntimeSpace(
        {Symbol("+"): (lambda *args: 0)},
        create_standard_runtime_space(),
    )

    ops = _collect_pure_ops(env)

    assert "+" not in ops
