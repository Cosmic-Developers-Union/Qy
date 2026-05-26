# coding: utf-8
"""测试 number-ss 算子内核 (qy.session.number_ops) 的语义。.

``+ - * /`` 要求所有参数为同一 concrete ``NumberValue`` 类型，
不接受 raw Python int/float；类型不一致触发 ``unsupported-operation`` effect；
除零触发 ``divide-by-zero`` effect。
"""

from __future__ import annotations

import pytest

from qy.core.syntax import nil as QY_NIL
from qy.errors import QyEffectSignal
from qy.sem.core import FloatValue
from qy.sem.core import Int32Value
from qy.sem.core import IntValue
from qy.sem.core import T as QY_T
from qy.session.number_ops import _add
from qy.session.number_ops import _div
from qy.session.number_ops import _mul
from qy.session.number_ops import _num_eq
from qy.session.number_ops import _py_eq
from qy.session.number_ops import _sub


def _i(n: int) -> IntValue:
    return IntValue(n)


def _f(x: float) -> FloatValue:
    return FloatValue(x)


def test_add_int_values_returns_int_value():
    assert _add(_i(1), _i(2), _i(3), _i(4)) == _i(10)


def test_add_floats_returns_float_value():
    assert _add(_f(1.5), _f(2.5), _f(3.0)) == _f(7.0)


def test_sub_single_arg_negates():
    assert _sub(_i(5)) == _i(-5)


def test_sub_multiple_args():
    assert _sub(_i(10), _i(3), _i(2)) == _i(5)


def test_mul_int_values():
    assert _mul(_i(2), _i(3), _i(4)) == _i(24)


def test_mul_floats():
    assert _mul(_f(2.5), _f(4.0)) == _f(10.0)


def test_div_single_int_value_truncates_to_zero():
    # 1 // 4 truncates to 0 in integer space.
    assert _div(_i(4)) == _i(0)


def test_div_single_float_returns_reciprocal():
    assert _div(_f(4.0)) == _f(0.25)


def test_div_multiple_int_values():
    assert _div(_i(20), _i(2), _i(2)) == _i(5)


def test_div_multiple_floats():
    assert _div(_f(10.0), _f(2.5)) == _f(4.0)


def test_div_by_zero_raises_effect():
    with pytest.raises(QyEffectSignal) as exc_info:
        _div(_i(10), _i(0))
    assert exc_info.value.effect == "divide-by-zero"


def test_div_by_zero_float_raises_effect():
    with pytest.raises(QyEffectSignal) as exc_info:
        _div(_f(10.0), _f(0.0))
    assert exc_info.value.effect == "divide-by-zero"


def test_mixed_concrete_types_trigger_unsupported_operation():
    with pytest.raises(QyEffectSignal) as exc_info:
        _add(_i(1), _f(2.0))
    assert exc_info.value.effect == "unsupported-operation"


def test_mixed_int_and_int32_trigger_unsupported_operation():
    with pytest.raises(QyEffectSignal) as exc_info:
        _add(_i(1), Int32Value(2))
    assert exc_info.value.effect == "unsupported-operation"


def test_add_promotes_raw_python_int_to_int_value():
    # Raw Python int is treated as a host literal and coerced to IntValue
    # at the operator boundary, so the call still produces NumberValue.
    assert _add(1, 2) == _i(3)


def test_add_rejects_string():
    with pytest.raises(QyEffectSignal) as exc_info:
        _add(_i(1), "not a number")
    assert exc_info.value.effect == "unsupported-operation"


def test_py_eq_equal_values():
    assert _py_eq(42, 42) is QY_T
    assert _py_eq("hello", "hello") is QY_T


def test_py_eq_unequal_values():
    assert _py_eq(42, 43) is QY_NIL
    assert _py_eq("hello", "world") is QY_NIL


def test_num_eq_with_bools():
    assert _num_eq(True, True) is QY_T
    assert _num_eq(False, False) is QY_T
    assert _num_eq(True, False) is QY_NIL


def test_num_eq_with_int_values():
    assert _num_eq(_i(42), _i(42)) is QY_T
    assert _num_eq(_i(42), _i(43)) is QY_NIL


def test_num_eq_mixed_concrete_types_triggers_unsupported_operation():
    with pytest.raises(QyEffectSignal) as exc_info:
        _num_eq(_i(1), _f(1.0))
    assert exc_info.value.effect == "unsupported-operation"


def test_num_eq_with_non_numbers_uses_is():
    obj = object()
    assert _num_eq(obj, obj) is QY_T
    assert _num_eq(object(), object()) is QY_NIL
