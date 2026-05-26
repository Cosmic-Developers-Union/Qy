# coding: utf-8
"""Hardware-optimized numeric symbol spaces.

提供类型化的整数和浮点数空间，每个空间包含：
- 类型构造器（带范围检查）
- 类型化算术运算符
- 比较运算符
- 位运算符（整数）
- 常量（min, max, bits）

溢出行为：触发 numeric-overflow 效应，允许用户通过 handle 自定义处理。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import cast

from qy.core.operators import PureOperator
from qy.errors import QyEffectSignal
from qy.errors import QyTypeError
from qy.frontend.reader import Symbol
from qy.sem.core import IntValue
from qy.vm.instance.frame import QyContinuation

if TYPE_CHECKING:
    from qy.import_.module import StandardModule
    from qy.sem.core import IntegerValue
    from qy.sem.core import NumberValue

__all__ = [
    "make_float16_space",
    "make_float32_space",
    "make_float64_space",
    "make_float128_space",
    "make_int8_space",
    "make_int16_space",
    "make_int32_space",
    "make_int64_space",
    "make_uint8_space",
    "make_uint16_space",
    "make_uint32_space",
    "make_uint64_space",
]


def _make_integer_space(
    type_name: str,
    value_class: type[IntegerValue],
    min_value: int,
    max_value: int,
    bits: int,
) -> StandardModule:
    """Generate a hardware integer space module."""
    from qy.core.syntax import nil as QY_NIL
    from qy.import_.module import StandardModule
    from qy.sem.core import T as QY_T

    def _non_resumable_continuation(effect_name: str) -> QyContinuation:
        """Create a non-resumable continuation for numeric errors."""

        async def resume(value: object) -> object:
            return value

        return QyContinuation(effect_name, False, resume)

    def _check_overflow(result: int, operation: str) -> int:
        """Check for overflow and raise effect if needed."""
        if not (min_value <= result <= max_value):
            raise QyEffectSignal(
                "numeric-overflow",
                {
                    "type": type_name,
                    "operation": operation,
                    "result": result,
                    "min": min_value,
                    "max": max_value,
                },
                _non_resumable_continuation("numeric-overflow"),
                resumable=False,
            )
        return result

    def _ensure_type(value: object, op_name: str) -> int:
        """Ensure value is of the correct type and return raw int."""
        if not isinstance(value, value_class):
            raise QyTypeError(
                f"{type_name}.{op_name} expects {type_name}, got {type(value).__name__}",
                metadata={"expected": type_name, "got": type(value).__name__},
            )
        return cast(Any, value).value

    # Constructor
    def _constructor(value: object) -> IntegerValue:
        """Convert IntValue or IntegerValue to this hardware type."""
        from qy.sem.core import IntegerValue

        if isinstance(value, IntegerValue):
            raw = cast(Any, value).value
        elif isinstance(value, int):
            raw = value
        else:
            raise QyTypeError(
                f"{type_name} constructor expects integer, got {type(value).__name__}",
                metadata={"expected": "integer", "got": type(value).__name__},
            )

        if not (min_value <= raw <= max_value):
            raise QyEffectSignal(
                "numeric-overflow",
                {
                    "type": type_name,
                    "operation": "constructor",
                    "value": raw,
                    "min": min_value,
                    "max": max_value,
                },
                _non_resumable_continuation("numeric-overflow"),
                resumable=False,
            )
        return cast(Any, value_class)(raw)

    # Type predicate
    def _type_predicate(value: object) -> object:
        """Check if value is of this type."""
        return QY_T if isinstance(value, value_class) else QY_NIL

    # Arithmetic operators
    def _add(*args: object) -> IntegerValue:
        """Typed addition."""
        if not args:
            return cast(Any, value_class)(0)
        result = 0
        for arg in args:
            result += _ensure_type(arg, "+")
        return cast(Any, value_class)(_check_overflow(result, "+"))

    def _sub(first: object, *rest: object) -> IntegerValue:
        """Typed subtraction or negation."""
        first_val = _ensure_type(first, "-")
        if not rest:
            return cast(Any, value_class)(_check_overflow(-first_val, "-"))
        result = first_val
        for arg in rest:
            result -= _ensure_type(arg, "-")
        return cast(Any, value_class)(_check_overflow(result, "-"))

    def _mul(*args: object) -> IntegerValue:
        """Typed multiplication."""
        if not args:
            return cast(Any, value_class)(1)
        result = 1
        for arg in args:
            result *= _ensure_type(arg, "*")
        return cast(Any, value_class)(_check_overflow(result, "*"))

    def _div(first: object, *rest: object) -> IntegerValue:
        """Typed integer division (truncating)."""
        first_val = _ensure_type(first, "/")
        if not rest:
            if first_val == 0:
                raise QyEffectSignal(
                    "divide-by-zero",
                    {},
                    _non_resumable_continuation("divide-by-zero"),
                    resumable=False,
                )
            return cast(Any, value_class)(_check_overflow(1 // first_val, "/"))
        result = first_val
        for arg in rest:
            divisor = _ensure_type(arg, "/")
            if divisor == 0:
                raise QyEffectSignal(
                    "divide-by-zero",
                    {},
                    _non_resumable_continuation("divide-by-zero"),
                    resumable=False,
                )
            result //= divisor
        return cast(Any, value_class)(_check_overflow(result, "/"))

    def _mod(a: object, b: object) -> IntegerValue:
        """Typed modulus."""
        a_val = _ensure_type(a, "mod")
        b_val = _ensure_type(b, "mod")
        if b_val == 0:
            raise QyEffectSignal(
                "divide-by-zero",
                {},
                _non_resumable_continuation("divide-by-zero"),
                resumable=False,
            )
        return cast(Any, value_class)(_check_overflow(a_val % b_val, "mod"))

    def _rem(a: object, b: object) -> IntegerValue:
        """Typed remainder."""
        a_val = _ensure_type(a, "rem")
        b_val = _ensure_type(b, "rem")
        if b_val == 0:
            raise QyEffectSignal(
                "divide-by-zero",
                {},
                _non_resumable_continuation("divide-by-zero"),
                resumable=False,
            )
        return cast(Any, value_class)(_check_overflow(a_val % b_val, "rem"))

    # Comparison operators
    def _lt(a: object, b: object) -> object:
        """Less than."""
        return QY_T if _ensure_type(a, "<") < _ensure_type(b, "<") else QY_NIL

    def _gt(a: object, b: object) -> object:
        """Greater than."""
        return QY_T if _ensure_type(a, ">") > _ensure_type(b, ">") else QY_NIL

    def _le(a: object, b: object) -> object:
        """Less than or equal."""
        return QY_T if _ensure_type(a, "<=") <= _ensure_type(b, "<=") else QY_NIL

    def _ge(a: object, b: object) -> object:
        """Greater than or equal."""
        return QY_T if _ensure_type(a, ">=") >= _ensure_type(b, ">=") else QY_NIL

    def _eq(a: object, b: object) -> object:
        """Typed equality."""
        if not isinstance(a, value_class) or not isinstance(b, value_class):
            return QY_NIL
        return QY_T if cast(Any, a).value == cast(Any, b).value else QY_NIL

    # Bitwise operators
    def _bit_and(*args: object) -> IntegerValue:
        """Bitwise AND."""
        if not args:
            return cast(Any, value_class)(-1)  # All bits set
        result = _ensure_type(args[0], "bit-and")
        for arg in args[1:]:
            result &= _ensure_type(arg, "bit-and")
        return cast(Any, value_class)(result)

    def _bit_or(*args: object) -> IntegerValue:
        """Bitwise OR."""
        if not args:
            return cast(Any, value_class)(0)
        result = _ensure_type(args[0], "bit-or")
        for arg in args[1:]:
            result |= _ensure_type(arg, "bit-or")
        return cast(Any, value_class)(result)

    def _bit_xor(*args: object) -> IntegerValue:
        """Bitwise XOR."""
        if not args:
            return cast(Any, value_class)(0)
        result = _ensure_type(args[0], "bit-xor")
        for arg in args[1:]:
            result ^= _ensure_type(arg, "bit-xor")
        return cast(Any, value_class)(result)

    def _bit_not(a: object) -> IntegerValue:
        """Bitwise NOT."""
        val = _ensure_type(a, "bit-not")
        # For fixed-width types, NOT should wrap within the type's range
        mask = (1 << bits) - 1
        result = (~val) & mask
        # Adjust for signed types
        if min_value < 0 and result >= (1 << (bits - 1)):
            result -= 1 << bits
        return cast(Any, value_class)(result)

    def _shl(a: object, b: object) -> IntegerValue:
        """Shift left."""
        a_val = _ensure_type(a, "shl")
        if isinstance(b, value_class):
            b_val = cast(Any, b).value
        elif isinstance(b, int):
            b_val = b
        else:
            raise QyTypeError(f"shl shift amount must be integer, got {type(b).__name__}")
        result = a_val << b_val
        return cast(Any, value_class)(_check_overflow(result, "shl"))

    def _shr(a: object, b: object) -> IntegerValue:
        """Shift right (arithmetic for signed, logical for unsigned)."""
        a_val = _ensure_type(a, "shr")
        if isinstance(b, value_class):
            b_val = cast(Any, b).value
        elif isinstance(b, int):
            b_val = b
        else:
            raise QyTypeError(f"shr shift amount must be integer, got {type(b).__name__}")
        result = a_val >> b_val
        return cast(Any, value_class)(result)

    # Build exports
    exports = {
        Symbol(type_name): PureOperator(type_name, _constructor, f"{type_name} 构造器"),
        Symbol(f"{type_name}?"): PureOperator(
            f"{type_name}?", _type_predicate, f"{type_name} 类型谓词"
        ),
        Symbol("+"): PureOperator("+", _add, f"{type_name} 加法"),
        Symbol("-"): PureOperator("-", _sub, f"{type_name} 减法/取负"),
        Symbol("*"): PureOperator("*", _mul, f"{type_name} 乘法"),
        Symbol("/"): PureOperator("/", _div, f"{type_name} 整数除法"),
        Symbol("mod"): PureOperator("mod", _mod, f"{type_name} 模运算"),
        Symbol("rem"): PureOperator("rem", _rem, f"{type_name} 余数运算"),
        Symbol("<"): PureOperator("<", _lt, f"{type_name} 小于"),
        Symbol(">"): PureOperator(">", _gt, f"{type_name} 大于"),
        Symbol("<="): PureOperator("<=", _le, f"{type_name} 小于等于"),
        Symbol(">="): PureOperator(">=", _ge, f"{type_name} 大于等于"),
        Symbol("="): PureOperator("=", _eq, f"{type_name} 相等"),
        Symbol("bit-and"): PureOperator("bit-and", _bit_and, f"{type_name} 按位与"),
        Symbol("bit-or"): PureOperator("bit-or", _bit_or, f"{type_name} 按位或"),
        Symbol("bit-xor"): PureOperator("bit-xor", _bit_xor, f"{type_name} 按位异或"),
        Symbol("bit-not"): PureOperator("bit-not", _bit_not, f"{type_name} 按位取反"),
        Symbol("shl"): PureOperator("shl", _shl, f"{type_name} 左移"),
        Symbol("shr"): PureOperator("shr", _shr, f"{type_name} 右移"),
        Symbol("min-value"): cast(Any, value_class)(min_value),
        Symbol("max-value"): cast(Any, value_class)(max_value),
        Symbol("bits"): IntValue(bits),
    }

    return StandardModule(f"qy.{type_name}", exports)


def _make_float_space(
    type_name: str,
    value_class: type[NumberValue],
    bits: int,
) -> StandardModule:
    """Generate a hardware float space module."""
    from qy.core.syntax import nil as QY_NIL
    from qy.import_.module import StandardModule
    from qy.sem.core import T as QY_T

    def _non_resumable_continuation(effect_name: str) -> QyContinuation:
        """Create a non-resumable continuation for numeric errors."""

        async def resume(value: object) -> object:
            return value

        return QyContinuation(effect_name, False, resume)

    def _ensure_type(value: object, op_name: str) -> float:
        """Ensure value is of the correct type and return raw float."""
        if not isinstance(value, value_class):
            raise QyTypeError(
                f"{type_name}.{op_name} expects {type_name}, got {type(value).__name__}",
                metadata={"expected": type_name, "got": type(value).__name__},
            )
        return cast(Any, value).value

    # Constructor
    def _constructor(value: object) -> NumberValue:
        """Convert number to this float type."""
        from qy.sem.core import FloatValue
        from qy.sem.core import IntegerValue

        if isinstance(value, FloatValue | IntegerValue):
            raw = float(cast(Any, value).value)
        elif isinstance(value, int | float):
            raw = float(value)
        else:
            raise QyTypeError(
                f"{type_name} constructor expects number, got {type(value).__name__}",
                metadata={"expected": "number", "got": type(value).__name__},
            )

        # Check for inf/nan
        if raw != raw or abs(raw) == float("inf"):
            raise QyEffectSignal(
                "numeric-overflow",
                {"type": type_name, "operation": "constructor", "value": raw},
                _non_resumable_continuation("numeric-overflow"),
                resumable=False,
            )
        return cast(Any, value_class)(raw)

    # Type predicate
    def _type_predicate(value: object) -> object:
        """Check if value is of this type."""
        return QY_T if isinstance(value, value_class) else QY_NIL

    # Arithmetic operators
    def _add(*args: object) -> NumberValue:
        """Typed addition."""
        if not args:
            return cast(Any, value_class)(0.0)
        result = 0.0
        for arg in args:
            result += _ensure_type(arg, "+")
        if result != result or abs(result) == float("inf"):
            raise QyEffectSignal(
                "numeric-overflow",
                {"type": type_name, "operation": "+"},
                _non_resumable_continuation("numeric-overflow"),
                resumable=False,
            )
        return cast(Any, value_class)(result)

    def _sub(first: object, *rest: object) -> NumberValue:
        """Typed subtraction or negation."""
        first_val = _ensure_type(first, "-")
        if not rest:
            return cast(Any, value_class)(-first_val)
        result = first_val
        for arg in rest:
            result -= _ensure_type(arg, "-")
        if result != result or abs(result) == float("inf"):
            raise QyEffectSignal(
                "numeric-overflow",
                {"type": type_name, "operation": "-"},
                _non_resumable_continuation("numeric-overflow"),
                resumable=False,
            )
        return cast(Any, value_class)(result)

    def _mul(*args: object) -> NumberValue:
        """Typed multiplication."""
        if not args:
            return cast(Any, value_class)(1.0)
        result = 1.0
        for arg in args:
            result *= _ensure_type(arg, "*")
        if result != result or abs(result) == float("inf"):
            raise QyEffectSignal(
                "numeric-overflow",
                {"type": type_name, "operation": "*"},
                _non_resumable_continuation("numeric-overflow"),
                resumable=False,
            )
        return cast(Any, value_class)(result)

    def _div(first: object, *rest: object) -> NumberValue:
        """Typed division."""
        first_val = _ensure_type(first, "/")
        if not rest:
            if first_val == 0.0:
                raise QyEffectSignal(
                    "divide-by-zero",
                    {},
                    _non_resumable_continuation("divide-by-zero"),
                    resumable=False,
                )
            result = 1.0 / first_val
        else:
            result = first_val
            for arg in rest:
                divisor = _ensure_type(arg, "/")
                if divisor == 0.0:
                    raise QyEffectSignal(
                        "divide-by-zero",
                        {},
                        _non_resumable_continuation("divide-by-zero"),
                        resumable=False,
                    )
                result /= divisor
        if result != result or abs(result) == float("inf"):
            raise QyEffectSignal(
                "numeric-overflow",
                {"type": type_name, "operation": "/"},
                _non_resumable_continuation("numeric-overflow"),
                resumable=False,
            )
        return cast(Any, value_class)(result)

    # Comparison operators
    def _lt(a: object, b: object) -> object:
        """Less than."""
        return QY_T if _ensure_type(a, "<") < _ensure_type(b, "<") else QY_NIL

    def _gt(a: object, b: object) -> object:
        """Greater than."""
        return QY_T if _ensure_type(a, ">") > _ensure_type(b, ">") else QY_NIL

    def _le(a: object, b: object) -> object:
        """Less than or equal."""
        return QY_T if _ensure_type(a, "<=") <= _ensure_type(b, "<=") else QY_NIL

    def _ge(a: object, b: object) -> object:
        """Greater than or equal."""
        return QY_T if _ensure_type(a, ">=") >= _ensure_type(b, ">=") else QY_NIL

    def _eq(a: object, b: object) -> object:
        """Typed equality."""
        if not isinstance(a, value_class) or not isinstance(b, value_class):
            return QY_NIL
        return QY_T if cast(Any, a).value == cast(Any, b).value else QY_NIL

    # Build exports
    exports = {
        Symbol(type_name): PureOperator(type_name, _constructor, f"{type_name} 构造器"),
        Symbol(f"{type_name}?"): PureOperator(
            f"{type_name}?", _type_predicate, f"{type_name} 类型谓词"
        ),
        Symbol("+"): PureOperator("+", _add, f"{type_name} 加法"),
        Symbol("-"): PureOperator("-", _sub, f"{type_name} 减法/取负"),
        Symbol("*"): PureOperator("*", _mul, f"{type_name} 乘法"),
        Symbol("/"): PureOperator("/", _div, f"{type_name} 除法"),
        Symbol("<"): PureOperator("<", _lt, f"{type_name} 小于"),
        Symbol(">"): PureOperator(">", _gt, f"{type_name} 大于"),
        Symbol("<="): PureOperator("<=", _le, f"{type_name} 小于等于"),
        Symbol(">="): PureOperator(">=", _ge, f"{type_name} 大于等于"),
        Symbol("="): PureOperator("=", _eq, f"{type_name} 相等"),
        Symbol("bits"): IntValue(bits),
    }

    return StandardModule(f"qy.{type_name}", exports)


# Integer space factories
def make_int8_space() -> StandardModule:
    """Create qy.int8 module."""
    from qy.sem.core import Int8Value

    return _make_integer_space("int8", Int8Value, -(2**7), 2**7 - 1, 8)


def make_int16_space() -> StandardModule:
    """Create qy.int16 module."""
    from qy.sem.core import Int16Value

    return _make_integer_space("int16", Int16Value, -(2**15), 2**15 - 1, 16)


def make_int32_space() -> StandardModule:
    """Create qy.int32 module."""
    from qy.sem.core import Int32Value

    return _make_integer_space("int32", Int32Value, -(2**31), 2**31 - 1, 32)


def make_int64_space() -> StandardModule:
    """Create qy.int64 module."""
    from qy.sem.core import Int64Value

    return _make_integer_space("int64", Int64Value, -(2**63), 2**63 - 1, 64)


def make_uint8_space() -> StandardModule:
    """Create qy.uint8 module."""
    from qy.sem.core import UInt8Value

    return _make_integer_space("uint8", UInt8Value, 0, 2**8 - 1, 8)


def make_uint16_space() -> StandardModule:
    """Create qy.uint16 module."""
    from qy.sem.core import UInt16Value

    return _make_integer_space("uint16", UInt16Value, 0, 2**16 - 1, 16)


def make_uint32_space() -> StandardModule:
    """Create qy.uint32 module."""
    from qy.sem.core import UInt32Value

    return _make_integer_space("uint32", UInt32Value, 0, 2**32 - 1, 32)


def make_uint64_space() -> StandardModule:
    """Create qy.uint64 module."""
    from qy.sem.core import UInt64Value

    return _make_integer_space("uint64", UInt64Value, 0, 2**64 - 1, 64)


# Float space factories
def make_float16_space() -> StandardModule:
    """Create qy.float16 module."""
    from qy.sem.core import Float16Value

    return _make_float_space("float16", Float16Value, 16)


def make_float32_space() -> StandardModule:
    """Create qy.float32 module."""
    from qy.sem.core import Float32Value

    return _make_float_space("float32", Float32Value, 32)


def make_float64_space() -> StandardModule:
    """Create qy.float64 module."""
    from qy.sem.core import FloatValue

    return _make_float_space("float64", FloatValue, 64)


def make_float128_space() -> StandardModule:
    """Create qy.float128 module."""
    from qy.sem.core import Float128Value

    return _make_float_space("float128", Float128Value, 128)
