# coding: utf-8
"""测试 qy.sem 模块的导出。."""

from __future__ import annotations

import qy.sem


def test_sem_exports_nil():
    """测试 NIL 常量导出。."""
    assert hasattr(qy.sem, "NIL")
    assert qy.sem.NIL is not None


def test_sem_exports_t():
    """测试 T 常量导出。."""
    assert hasattr(qy.sem, "T")
    assert qy.sem.T is not None


def test_sem_exports_value_types():
    """测试所有 Value 类型导出。."""
    expected_types = [
        "Value",
        "NilValue",
        "TValue",
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
        "SymbolValue",
        "ChainValue",
        "ArrayValue",
        "HashMapValue",
        "ObjectValue",
        "DatumValue",
    ]
    for type_name in expected_types:
        assert hasattr(qy.sem, type_name), f"Missing export: {type_name}"


def test_sem_all_list():
    """测试 __all__ 列表包含所有导出。."""
    assert hasattr(qy.sem, "__all__")
    assert isinstance(qy.sem.__all__, list)
    assert len(qy.sem.__all__) > 0
    # 验证 __all__ 中的所有名称都可以导入
    for name in qy.sem.__all__:
        assert hasattr(qy.sem, name), f"__all__ contains {name} but it's not exported"


def test_sem_value_instantiation():
    """测试可以实例化基本的 Value 类型。."""
    # IntValue
    int_val = qy.sem.IntValue(42)
    assert int_val.value == 42

    # FloatValue
    float_val = qy.sem.FloatValue(3.14)
    assert float_val.value == 3.14

    # StringValue
    str_val = qy.sem.StringValue("hello")
    assert str_val.value == "hello"

    # ChainValue
    chain_val = qy.sem.ChainValue(int_val, qy.sem.NIL)
    assert chain_val.head == int_val
    assert chain_val.tail == qy.sem.NIL
