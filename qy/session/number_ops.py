# coding: utf-8
"""Number-ss arithmetic operators.

这是 ``number-ss`` 的算子实现。number-ss 同时具备：

- 无限部分: 通过 ``parse_number_literal`` 识别所有数字字面量 (``42``, ``-3``,
  ``2.5``, ...) 并解析为 ``IntValue`` / ``FloatValue``。
- 有限部分: 持有 ``+ - * / = == < > <= >= mod`` 这套数字算子, 直接绑定在
  number-ss 内部, 与字面量并列。

每个算子先做"参数全部为同一 concrete ``NumberValue`` 类型"的一致性检查,
然后把实际算术 dispatch 到对应 number 类型的 kernel。这条 dispatch 路径
对应 LANGUAGE.md 中"`+` 委托给 number-ss 提供的 add 算子"的实现:
具体的 number 类型决定算术语义, ``+`` 本身只做一致性校验和分派。

不做隐式 promotion: ``(+ int32 int64)`` 不再静默升位, 而是触发
``unsupported-operation`` effect (由 handler 决定如何处理)。除零触发
``divide-by-zero`` effect。定宽整型/浮点的越界触发 ``numeric-overflow``
effect。这三个 effect 都是非可恢复 effect 的标准形态。

调用方:

- ``qy/session/pre_ss.py::create_number_ss`` 通过 ``number_ss_bindings()`` 注入。
- ``qy/symbol_space/__init__.py::_load_num_module`` 把同一份 bindings 暴露为 ``qy.num`` 模块。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from qy.core.operators import PureOperator
from qy.core.syntax import nil as QY_NIL
from qy.errors import QyEffectSignal
from qy.errors import QyTypeError
from qy.frontend.reader import Symbol
from qy.sem.core import Float16Value
from qy.sem.core import Float32Value
from qy.sem.core import Float128Value
from qy.sem.core import FloatValue
from qy.sem.core import Int8Value
from qy.sem.core import Int16Value
from qy.sem.core import Int32Value
from qy.sem.core import Int64Value
from qy.sem.core import IntegerValue
from qy.sem.core import IntValue
from qy.sem.core import NumberValue
from qy.sem.core import T as QY_T
from qy.sem.core import UInt8Value
from qy.sem.core import UInt16Value
from qy.sem.core import UInt32Value
from qy.sem.core import UInt64Value
from qy.vm.instance.frame import QyContinuation

__all__ = [
    "number_ss_bindings",
]


def _non_resumable_continuation(effect_name: str) -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation(effect_name, False, resume)


def _resumable_continuation(effect_name: str) -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation(effect_name, True, resume)


def _perform_effect(name: str, payload: object, *, resumable: bool = False) -> None:
    cont = _resumable_continuation(name) if resumable else _non_resumable_continuation(name)
    raise QyEffectSignal(
        name,
        payload,
        cont,
        resumable=resumable,
    )


# ---------------------------------------------------------------------------
# Per-concrete-type arithmetic kernels
# ---------------------------------------------------------------------------

# Integer types: dict maps the concrete value class to its (min, max) range.
# IntValue (arbitrary precision) is represented by ``None`` range.
_INTEGER_RANGES: dict[type[IntegerValue], tuple[int, int] | None] = {
    IntValue: None,
    Int8Value: (-(2**7), 2**7 - 1),
    Int16Value: (-(2**15), 2**15 - 1),
    Int32Value: (-(2**31), 2**31 - 1),
    Int64Value: (-(2**63), 2**63 - 1),
    UInt8Value: (0, 2**8 - 1),
    UInt16Value: (0, 2**16 - 1),
    UInt32Value: (0, 2**32 - 1),
    UInt64Value: (0, 2**64 - 1),
}

# Float types: any NumberValue subclass that wraps a Python float and is not
# an IntegerValue. We avoid implicit conversion across types, but each
# float-like type does the same Python-float arithmetic internally.
_FLOAT_TYPES: tuple[type[NumberValue], ...] = (
    FloatValue,
    Float16Value,
    Float32Value,
    Float128Value,
)


def _check_integer_range(value: int, value_type: type[IntegerValue], op: str) -> int:
    """Raise numeric-overflow effect when *value* falls outside the type range."""
    bounds = _INTEGER_RANGES.get(value_type)
    if bounds is None:
        return value
    minimum, maximum = bounds
    if not (minimum <= value <= maximum):
        _perform_effect(
            "numeric-overflow",
            {
                "type": value_type.type_name,
                "operation": op,
                "result": value,
                "min": minimum,
                "max": maximum,
            },
        )
    return value


def _check_float_finite(value: float, type_name: str, op: str) -> float:
    if value != value or abs(value) == float("inf"):
        _perform_effect(
            "numeric-overflow",
            {"type": type_name, "operation": op, "result": value},
        )
    return value


def _integer_payload(value: IntegerValue) -> int:
    return cast(int, value.value)


def _number_payload(value: NumberValue) -> int | float:
    return value.value


def _make_integer(value_type: type[IntegerValue], value: int) -> IntegerValue:
    return cast(Callable[[int], IntegerValue], value_type)(value)


def _make_number(value_type: type[NumberValue], value: int | float) -> NumberValue:
    return cast(Callable[[int | float], NumberValue], value_type)(value)


def _coerce_host_number(value: object) -> object:
    """Promote raw ``int``/``float`` host literals to ``NumberValue``."""
    if isinstance(value, NumberValue):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return IntValue(value)
    if isinstance(value, float):
        return FloatValue(value)
    return value


def _ensure_same_number_type(args: tuple[object, ...], op: str) -> type[NumberValue]:
    """Require every argument to be the same concrete ``NumberValue`` type."""
    if not args:
        raise QyTypeError(f"{op} requires at least one argument")
    head = args[0]
    if not isinstance(head, NumberValue):
        raise QyTypeError(
            f"{op} expects a number, got {type(head).__name__}",
            metadata={"operator": op, "value": head},
        )
    head_type = type(head)
    for index, arg in enumerate(args[1:], start=1):
        if type(arg) is not head_type:
            _perform_effect(
                "unsupported-operation",
                {
                    "operator": op,
                    "left_type": head_type.type_name,
                    "right_type": getattr(type(arg), "type_name", type(arg).__name__),
                    "argument_index": index,
                },
            )
    return head_type


def _dispatch_op(
    op: str,
    args: tuple[object, ...],
    integer_kernel: Callable[[type[IntegerValue], tuple[IntegerValue, ...]], IntegerValue],
    float_kernel: Callable[[type[NumberValue], tuple[NumberValue, ...]], NumberValue],
) -> NumberValue:
    args = tuple(_coerce_host_number(a) for a in args)
    value_type = _ensure_same_number_type(args, op)
    typed_args = tuple(arg for arg in args if isinstance(arg, NumberValue))
    if issubclass(value_type, IntegerValue):
        integer_args = tuple(arg for arg in typed_args if isinstance(arg, IntegerValue))
        return integer_kernel(value_type, integer_args)
    if value_type in _FLOAT_TYPES or any(issubclass(value_type, t) for t in _FLOAT_TYPES):
        return float_kernel(value_type, typed_args)
    raise QyTypeError(
        f"{op} has no kernel for number type {value_type.type_name}",
        metadata={"operator": op, "type": value_type.type_name},
    )


# -- Integer kernels ---------------------------------------------------------


def _integer_add(value_type: type[IntegerValue], args: tuple[IntegerValue, ...]) -> IntegerValue:
    total = 0
    for arg in args:
        total += _integer_payload(arg)
    return _make_integer(value_type, _check_integer_range(total, value_type, "+"))


def _integer_sub(value_type: type[IntegerValue], args: tuple[IntegerValue, ...]) -> IntegerValue:
    if len(args) == 1:
        return _make_integer(
            value_type, _check_integer_range(-_integer_payload(args[0]), value_type, "-")
        )
    result = _integer_payload(args[0])
    for arg in args[1:]:
        result -= _integer_payload(arg)
    return _make_integer(value_type, _check_integer_range(result, value_type, "-"))


def _integer_mul(value_type: type[IntegerValue], args: tuple[IntegerValue, ...]) -> IntegerValue:
    result = 1
    for arg in args:
        result *= _integer_payload(arg)
    return _make_integer(value_type, _check_integer_range(result, value_type, "*"))


def _integer_div(value_type: type[IntegerValue], args: tuple[IntegerValue, ...]) -> IntegerValue:
    if len(args) == 1:
        first = _integer_payload(args[0])
        if first == 0:
            _perform_effect("divide-by-zero", {"operator": "/"}, resumable=True)
        return _make_integer(value_type, _check_integer_range(1 // first, value_type, "/"))
    result = _integer_payload(args[0])
    for arg in args[1:]:
        divisor = _integer_payload(arg)
        if divisor == 0:
            _perform_effect("divide-by-zero", {"operator": "/"}, resumable=True)
        # Truncating integer division (``//`` in Python rounds toward -inf;
        # Qy uses truncation semantics consistent with C-style integer ops).
        result = (
            int(result / divisor)
            if (result < 0) ^ (divisor < 0) and result % divisor
            else result // divisor
        )
    return _make_integer(value_type, _check_integer_range(result, value_type, "/"))


def _integer_mod(value_type: type[IntegerValue], args: tuple[IntegerValue, ...]) -> IntegerValue:
    if len(args) != 2:
        raise QyTypeError("mod expects exactly 2 arguments")
    a = _integer_payload(args[0])
    b = _integer_payload(args[1])
    if b == 0:
        _perform_effect("divide-by-zero", {"operator": "mod"}, resumable=False)
    return _make_integer(value_type, _check_integer_range(a % b, value_type, "mod"))


# -- Float kernels -----------------------------------------------------------


def _float_add(value_type: type[NumberValue], args: tuple[NumberValue, ...]) -> NumberValue:
    total = 0.0
    for arg in args:
        total += float(_number_payload(arg))
    return _make_number(value_type, _check_float_finite(total, value_type.type_name, "+"))


def _float_sub(value_type: type[NumberValue], args: tuple[NumberValue, ...]) -> NumberValue:
    if len(args) == 1:
        return _make_number(value_type, -float(_number_payload(args[0])))
    result = float(_number_payload(args[0]))
    for arg in args[1:]:
        result -= float(_number_payload(arg))
    return _make_number(value_type, _check_float_finite(result, value_type.type_name, "-"))


def _float_mul(value_type: type[NumberValue], args: tuple[NumberValue, ...]) -> NumberValue:
    result = 1.0
    for arg in args:
        result *= float(_number_payload(arg))
    return _make_number(value_type, _check_float_finite(result, value_type.type_name, "*"))


def _float_div(value_type: type[NumberValue], args: tuple[NumberValue, ...]) -> NumberValue:
    if len(args) == 1:
        first = float(_number_payload(args[0]))
        if first == 0.0:
            _perform_effect("divide-by-zero", {"operator": "/"}, resumable=True)
        return _make_number(value_type, _check_float_finite(1.0 / first, value_type.type_name, "/"))
    result = float(_number_payload(args[0]))
    for arg in args[1:]:
        divisor = float(_number_payload(arg))
        if divisor == 0.0:
            _perform_effect("divide-by-zero", {"operator": "/"}, resumable=True)
        result /= divisor
    return _make_number(value_type, _check_float_finite(result, value_type.type_name, "/"))


def _float_mod(value_type: type[NumberValue], args: tuple[NumberValue, ...]) -> NumberValue:
    if len(args) != 2:
        raise QyTypeError("mod expects exactly 2 arguments")
    a = float(_number_payload(args[0]))
    b = float(_number_payload(args[1]))
    if b == 0.0:
        _perform_effect("divide-by-zero", {"operator": "mod"}, resumable=False)
    return _make_number(
        value_type, _check_float_finite(a - b * int(a / b), value_type.type_name, "mod")
    )


# -- Public arithmetic operators --------------------------------------------


def _add(*args: object) -> NumberValue:
    return _dispatch_op("+", args, _integer_add, _float_add)


def _sub(*args: object) -> NumberValue:
    return _dispatch_op("-", args, _integer_sub, _float_sub)


def _mul(*args: object) -> NumberValue:
    return _dispatch_op("*", args, _integer_mul, _float_mul)


def _div(*args: object) -> NumberValue:
    return _dispatch_op("/", args, _integer_div, _float_div)


def _mod(*args: object) -> NumberValue:
    return _dispatch_op("mod", args, _integer_mod, _float_mod)


# -- Comparison operators ----------------------------------------------------


def _ordering(
    op: str,
    args: tuple[object, ...],
    py_op: Callable[[int | float, int | float], bool],
) -> object:
    if len(args) != 2:
        raise QyTypeError(f"{op} expects exactly 2 arguments")
    coerced = tuple(_coerce_host_number(a) for a in args)
    _ensure_same_number_type(coerced, op)
    left, right = coerced
    if not isinstance(left, NumberValue) or not isinstance(right, NumberValue):
        raise QyTypeError(f"{op} expects numbers")
    return QY_T if py_op(_number_payload(left), _number_payload(right)) else QY_NIL


def _lt(*args: object) -> object:
    return _ordering("<", args, lambda a, b: a < b)


def _gt(*args: object) -> object:
    return _ordering(">", args, lambda a, b: a > b)


def _le(*args: object) -> object:
    return _ordering("<=", args, lambda a, b: a <= b)


def _ge(*args: object) -> object:
    return _ordering(">=", args, lambda a, b: a >= b)


def _num_eq(left: object, right: object) -> object:
    """Numeric equality across same-type ``NumberValue`` operands."""
    if isinstance(left, bool) or isinstance(right, bool):
        return QY_T if left is right else QY_NIL
    left = _coerce_host_number(left)
    right = _coerce_host_number(right)
    if isinstance(left, NumberValue) and isinstance(right, NumberValue):
        if type(left) is not type(right):
            _perform_effect(
                "unsupported-operation",
                {
                    "operator": "=",
                    "left_type": type(left).type_name,
                    "right_type": type(right).type_name,
                },
            )
        return QY_T if left.value == right.value else QY_NIL  # type: ignore[attr-defined]
    return QY_T if left is right else QY_NIL


def _py_eq(left: object, right: object) -> object:
    return QY_T if left == right else QY_NIL


def number_ss_bindings() -> dict[Symbol, object]:
    """Return the fixed bindings of number-ss.

    These are the numeric operators that live inside number-ss alongside its
    infinite literal recognition. Used by:

    - ``qy/session/pre_ss.py::create_number_ss`` — number-ss 自身。
    - ``qy/symbol_space/__init__.py::_load_num_module`` — ``qy.num`` 模块导出 (用户脚本
      可显式 ``(from qy.num import +)``)。
    """
    return {
        Symbol("="): PureOperator("=", _num_eq, "数值相等比较；要求同 concrete number 类型。"),
        Symbol("=="): PureOperator("==", _py_eq, "按 Python == 语义比较两个值。（兼容层）"),
        Symbol("+"): PureOperator("+", _add, "数字求和；要求所有参数为同一 concrete number 类型。"),
        Symbol("-"): PureOperator(
            "-", _sub, "数字相减；单参数取负；要求所有参数为同一 concrete number 类型。"
        ),
        Symbol("*"): PureOperator("*", _mul, "数字相乘；要求所有参数为同一 concrete number 类型。"),
        Symbol("/"): PureOperator(
            "/",
            _div,
            "数字相除；要求所有参数为同一 concrete number 类型；除零触发 divide-by-zero effect。",
        ),
        Symbol("mod"): PureOperator("mod", _mod, "取模；要求所有参数为同一 concrete number 类型。"),
        Symbol("<"): PureOperator("<", _lt, "小于;要求所有参数为同一 concrete number 类型。"),
        Symbol(">"): PureOperator(">", _gt, "大于;要求所有参数为同一 concrete number 类型。"),
        Symbol("<="): PureOperator("<=", _le, "小于等于;要求所有参数为同一 concrete number 类型。"),
        Symbol(">="): PureOperator(">=", _ge, "大于等于;要求所有参数为同一 concrete number 类型。"),
    }
