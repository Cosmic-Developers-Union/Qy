# coding: utf-8
"""测试 qy.sem.bridge 模块。."""

from __future__ import annotations

from qy.sem.bridge import from_sem
from qy.sem.bridge import to_sem
from qy.sem.core import NIL
from qy.sem.core import ChainValue
from qy.sem.core import FloatValue
from qy.sem.core import IntValue
from qy.sem.core import NilValue
from qy.sem.core import StringValue
from qy.sem.core import T
from qy.sem.core import TValue
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyChain


def test_to_sem_nil():
    """测试 QY_NIL 转换为 sem NIL。."""
    assert to_sem(QY_NIL) == NIL
    assert to_sem(None) == NIL


def test_to_sem_t():
    """测试 QY_T 转换为 sem T。."""
    assert to_sem(QY_T) == T
    assert to_sem(True) == T


def test_to_sem_int():
    """测试整数转换为 IntValue。."""
    result = to_sem(42)
    assert isinstance(result, IntValue)
    assert result.value == 42


def test_to_sem_float():
    """测试浮点数转换为 FloatValue。."""
    result = to_sem(3.14)
    assert isinstance(result, FloatValue)
    assert result.value == 3.14


def test_to_sem_string():
    """测试字符串转换为 StringValue。."""
    result = to_sem("hello")
    assert isinstance(result, StringValue)
    assert result.value == "hello"


def test_to_sem_chain():
    """测试 QyChain 转换为 ChainValue。."""
    chain = QyChain(42, QY_NIL)
    result = to_sem(chain)
    assert isinstance(result, ChainValue)
    assert isinstance(result.head, IntValue)
    assert result.head.value == 42
    assert result.tail == NIL


def test_to_sem_already_sem_value():
    """测试已经是 sem Value 的值直接返回。."""
    value = IntValue(100)
    assert to_sem(value) is value


def test_to_sem_unknown_type():
    """测试未知类型转换为 NIL。."""
    result = to_sem(object())
    assert result == NIL


def test_from_sem_nil():
    """测试 NIL 转换为 QY_NIL。."""
    assert from_sem(NIL) is QY_NIL
    assert from_sem(NilValue()) is QY_NIL


def test_from_sem_t():
    """测试 T 转换为 QY_T。."""
    assert from_sem(T) is QY_T
    assert from_sem(TValue()) is QY_T


def test_from_sem_int():
    """测试 IntValue 转换为 Python int。."""
    result = from_sem(IntValue(42))
    assert result == 42
    assert isinstance(result, int)


def test_from_sem_float():
    """测试 FloatValue 转换为 Python float。."""
    result = from_sem(FloatValue(3.14))
    assert result == 3.14
    assert isinstance(result, float)


def test_from_sem_string():
    """测试 StringValue 转换为 Python str。."""
    result = from_sem(StringValue("hello"))
    assert result == "hello"
    assert isinstance(result, str)


def test_from_sem_chain():
    """测试 ChainValue 转换为 QyChain。."""
    chain_value = ChainValue(IntValue(42), NIL)
    result = from_sem(chain_value)
    assert isinstance(result, QyChain)
    assert result.head == 42
    assert result.tail is QY_NIL


def test_roundtrip_conversion():
    """测试往返转换保持值不变。."""
    original = QyChain(42, QyChain("hello", QY_NIL))
    sem_value = to_sem(original)
    back = from_sem(sem_value)
    assert isinstance(back, QyChain)
    assert back.head == 42
    assert isinstance(back.tail, QyChain)
    assert back.tail.head == "hello"
    assert back.tail.tail is QY_NIL
