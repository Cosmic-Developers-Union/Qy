# coding: utf-8
"""测试 qy.sem 与 qy.core.syntax 的值模型边界。."""

from __future__ import annotations

import qy.sem
from qy.core.syntax import NONE
from qy.core.syntax import Chain
from qy.core.syntax import NoneValue
from qy.core.syntax import QyNil
from qy.core.syntax import T
from qy.core.syntax import TValue
from qy.core.syntax import nil

# qy.sem 只负责 number / string / object family；datum 与 Qy 自身对象
# 的真源是 qy.core.syntax。
_SEM_VALUE_TYPES = [
    "Value",
    "NumberValue",
    "IntegerValue",
    "IntValue",
    "Int32Value",
    "Int64Value",
    "FloatValue",
    "Float32Value",
    "RationalValue",
    "ComplexValue",
    "StringValue",
    "CharValue",
    "ArrayValue",
    "HashMapValue",
    "ObjectValue",
]

# 这些名字不得再出现在 qy.sem：它们属于 qy.core.syntax。
_CORE_ONLY_NAMES = [
    "NIL",
    "T",
    "NONE",
    "NilValue",
    "TValue",
    "NoneValue",
    "SymbolValue",
    "ChainValue",
    "DatumValue",
]


def test_core_syntax_owns_self_objects():
    """Nil / T / none 三个 Qy 自身对象同处 qy.core.syntax。."""
    assert isinstance(nil, QyNil)
    assert isinstance(T, TValue)
    assert isinstance(NONE, NoneValue)
    assert str(T) == "T"
    assert str(NONE) == "none"


def test_sem_exports_value_types():
    """qy.sem 导出 number / string / object family 值类型。."""
    for type_name in _SEM_VALUE_TYPES:
        assert hasattr(qy.sem, type_name), f"Missing export: {type_name}"


def test_sem_does_not_own_datums():
    """qy.sem 不得重复定义 datum 与 Qy 自身对象。."""
    for name in _CORE_ONLY_NAMES:
        assert not hasattr(qy.sem, name), f"qy.sem must not export {name}"


def test_sem_all_list():
    """测试 __all__ 列表包含所有导出。."""
    assert hasattr(qy.sem, "__all__")
    assert isinstance(qy.sem.__all__, list)
    assert len(qy.sem.__all__) > 0
    for name in qy.sem.__all__:
        assert hasattr(qy.sem, name), f"__all__ contains {name} but it's not exported"


def test_sem_value_instantiation():
    """测试可以实例化基本的 Value 类型。."""
    int_val = qy.sem.IntValue(42)
    assert int_val.value == 42

    float_val = qy.sem.FloatValue(3.14)
    assert float_val.value == 3.14

    str_val = qy.sem.StringValue("hello")
    assert str_val.value == "hello"

    # chain 的语义表示就是 qy.core.syntax.Chain，其空尾就是 nil。
    chain_val = Chain(int_val, nil)
    assert chain_val.head == int_val
    assert chain_val.tail is nil
