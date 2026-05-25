# coding: utf-8
"""测试 qy.vm.instance.values 模块。."""

from __future__ import annotations

from qy.vm.instance.values import HostObjectRef
from qy.vm.instance.values import TailCall


def test_host_object_ref_creation():
    """测试创建 HostObjectRef。."""
    obj = {"key": "value"}
    ref = HostObjectRef(value=obj)
    assert ref.value is obj


def test_host_object_ref_wraps_any_object():
    """测试 HostObjectRef 可以包装任何对象。."""
    # 包装字典
    dict_ref = HostObjectRef(value={"a": 1})
    assert dict_ref.value == {"a": 1}

    # 包装列表
    list_ref = HostObjectRef(value=[1, 2, 3])
    assert list_ref.value == [1, 2, 3]

    # 包装函数
    def func():
        return 42

    func_ref = HostObjectRef(value=func)
    assert func_ref.value() == 42  # ty: ignore[call-non-callable]

    # 包装类实例
    class TestClass:
        def __init__(self, x: int):
            self.x = x

    obj = TestClass(10)
    obj_ref = HostObjectRef(value=obj)
    assert obj_ref.value.x == 10  # ty: ignore[unresolved-attribute]


def test_host_object_ref_equality():
    """测试 HostObjectRef 的相等性。.

    HostObjectRef 使用 eq=False，所以即使包装相同的对象，
    两个不同的 HostObjectRef 实例也不相等。
    """
    obj = {"key": "value"}
    ref1 = HostObjectRef(value=obj)
    ref2 = HostObjectRef(value=obj)

    # 不同的 HostObjectRef 实例不相等（eq=False）
    assert ref1 is not ref2
    # 但包装的对象是同一个
    assert ref1.value is ref2.value


def test_tail_call_creation():
    """测试创建 TailCall。."""

    def test_func(x: int) -> int:
        return x + 1

    tail_call = TailCall(function=test_func, args=(42,))
    assert tail_call.function is test_func
    assert tail_call.args == (42,)


def test_tail_call_with_multiple_args():
    """测试带多个参数的 TailCall。."""

    def test_func(x: int, y: int, z: int) -> int:
        return x + y + z

    tail_call = TailCall(function=test_func, args=(1, 2, 3))
    assert tail_call.function is test_func
    assert tail_call.args == (1, 2, 3)


def test_tail_call_with_no_args():
    """测试不带参数的 TailCall。."""

    def test_func() -> int:
        return 42

    tail_call = TailCall(function=test_func, args=())
    assert tail_call.function is test_func
    assert tail_call.args == ()


def test_tail_call_immutable():
    """测试 TailCall 是不可变的。."""

    def test_func(x: int) -> int:
        return x

    tail_call = TailCall(function=test_func, args=(42,))

    try:
        tail_call.function = lambda x: x + 1  # ty: ignore[invalid-assignment]
        raise AssertionError("应该抛出 AttributeError")
    except AttributeError:
        pass

    try:
        tail_call.args = (100,)  # ty: ignore[invalid-assignment]
        raise AssertionError("应该抛出 AttributeError")
    except AttributeError:
        pass


def test_tail_call_equality():
    """测试 TailCall 的相等性。."""

    def test_func(x: int) -> int:
        return x

    tail_call1 = TailCall(function=test_func, args=(42,))
    tail_call2 = TailCall(function=test_func, args=(42,))

    # 相同的函数和参数应该相等
    assert tail_call1 == tail_call2
    assert tail_call1.function is tail_call2.function
    assert tail_call1.args == tail_call2.args


def test_tail_call_inequality():
    """测试 TailCall 的不等性。."""

    def test_func1(x: int) -> int:
        return x

    def test_func2(x: int) -> int:
        return x + 1

    tail_call1 = TailCall(function=test_func1, args=(42,))
    tail_call2 = TailCall(function=test_func2, args=(42,))
    tail_call3 = TailCall(function=test_func1, args=(100,))

    # 不同的函数
    assert tail_call1 != tail_call2

    # 不同的参数
    assert tail_call1 != tail_call3


def test_host_object_ref_immutable():
    """测试 HostObjectRef 是不可变的。."""
    obj = {"key": "value"}
    ref = HostObjectRef(value=obj)

    try:
        ref.value = {"new": "value"}  # ty: ignore[invalid-assignment]
        raise AssertionError("应该抛出 AttributeError")
    except AttributeError:
        pass
