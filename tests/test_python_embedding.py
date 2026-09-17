# coding: utf-8
"""宿主与 Qy 之间的值转换、以及宿主调用 Qy 函数值的嵌入式 API。.

这是"Qy 作为嵌入式语言在 Python 中工作"的核心契约：

- `qy.sem.convert.to_qy_value` / `from_qy_value`：宿主值 ↔ Qy 语义值的**唯一**转换实现
  （扩展与嵌入式宿主共用，不得各自再写一份）；
- `Qy.call` / `AsyncQy.call`：宿主直接调用 Qy 函数值（`lambda` / `defun` 的结果）。
"""

from __future__ import annotations

import asyncio

import pytest

from qy.core.syntax import T
from qy.core.syntax import nil
from qy.errors import QyTypeError
from qy.runtime import AsyncQy
from qy.runtime import Qy
from qy.sem.convert import from_qy_value
from qy.sem.convert import to_qy_value
from qy.sem.core import DictValue
from qy.sem.core import IntValue
from qy.sem.core import ListValue
from qy.sem.core import StringValue
from qy.sem.core import TupleValue
from qy.sem.host import HostReference


class _HostObject:
    """一个普通宿主对象（不可转成 Qy 值，应被包装为 HostReference）。。."""


def test_host_primitives_convert_to_qy_values():
    assert isinstance(to_qy_value("a"), StringValue)
    assert isinstance(to_qy_value([1, 2]), ListValue)
    assert isinstance(to_qy_value((1, 2)), TupleValue)
    assert isinstance(to_qy_value({"k": 1}), DictValue)
    # 数字保持宿主原生（边界上不强制包装成 IntValue）
    assert to_qy_value(3) == 3


def test_host_singletons_pass_through():
    assert to_qy_value(nil) is nil
    assert to_qy_value(T) is T


def test_unknown_host_object_becomes_host_reference():
    obj = _HostObject()

    wrapped = to_qy_value(obj)

    assert isinstance(wrapped, HostReference)
    assert wrapped.value is obj
    assert from_qy_value(wrapped) is obj


def test_from_qy_value_unwraps_scalars_and_containers():
    assert from_qy_value(StringValue("a")) == "a"
    assert from_qy_value(IntValue(3)) == 3
    assert from_qy_value(ListValue((IntValue(1), StringValue("b")))) == [1, "b"]
    assert from_qy_value(DictValue(((StringValue("k"), IntValue(1)),))) == {"k": 1}


def test_language_level_values_are_not_unwrapped():
    """Nil / T / none 与函数值没有忠实宿主对应物，解包必须原样返回。。."""
    assert from_qy_value(nil) is nil
    assert from_qy_value(T) is T


def test_nested_host_containers_convert_recursively():
    converted = to_qy_value({"items": [1, "a"], "flag": True})

    assert isinstance(converted, DictValue)
    unwrapped = from_qy_value(converted)
    assert unwrapped == {"items": [1, "a"], "flag": True}


def test_python_extension_delegates_to_shared_conversion():
    """扩展侧不得再保留第二份转换实现。。."""
    import qy.ext.python as python_ext

    source = python_ext.__dict__
    assert "_python_to_qy" in source
    obj = _HostObject()
    assert isinstance(python_ext._python_to_qy(obj), HostReference)


def test_qy_call_invokes_a_qy_function_value():
    qy = Qy()
    increment = qy.evaluate_source("(lambda (x) (+ x 1))")

    result = qy.call(increment, to_qy_value(41))

    assert from_qy_value(result) == 42


def test_qy_call_supports_recursive_functions():
    qy = Qy()
    factorial = qy.evaluate_source(
        "(defun fact (n) (cond ((= n 0) 1) ((< 0 n) (* n (fact (- n 1))))))"
    )

    result = qy.call(factorial, to_qy_value(5))

    assert from_qy_value(result) == 120


def test_qy_call_rejects_non_function_values():
    qy = Qy()

    with pytest.raises(QyTypeError, match="expects a Qy function value"):
        qy.call(42)


def test_qy_call_passes_host_objects_as_host_references():
    """宿主对象经转换后可在 Qy 侧被当作不透明值传递。。."""
    qy = Qy()
    identity = qy.evaluate_source("(lambda (x) x)")
    obj = _HostObject()

    result = qy.call(identity, to_qy_value(obj))

    assert from_qy_value(result) is obj


def test_async_qy_call_invokes_a_qy_function_value():
    async def main() -> object:
        qy = AsyncQy()
        add = await qy.evaluate_source("(lambda (a b) (+ a b))")
        return await qy.call(add, to_qy_value(20), to_qy_value(22))

    assert from_qy_value(asyncio.run(main())) == 42
