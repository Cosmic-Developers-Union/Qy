# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Core runtime value model shared by every Qy backend.

This module describes *semantic* runtime values, not Python implementation
helpers.  Register VM, libqy, LLVM, and later backends must converge on this
model even when their physical representations differ.

Important rule for the number family:

- numeric values may belong to the same family while still being different
  concrete semantic types;
- Qy does not apply implicit numeric conversion;
- an operation such as ``(+ int32 int64)`` is not silently promoted.  It is an
  unsupported mixed-type operation and must be handled through the language's
  effect/error path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

__all__ = [
    "NIL",
    "ArrayValue",
    "ChainValue",
    "CharValue",
    "ComplexValue",
    "DatumValue",
    "Float16Value",
    "Float32Value",
    "Float64Value",
    "Float128Value",
    "FloatValue",
    "HashMapValue",
    "Int8Value",
    "Int16Value",
    "Int32Value",
    "Int64Value",
    "IntValue",
    "IntegerValue",
    "NilValue",
    "NumberValue",
    "ObjectValue",
    "RationalValue",
    "StringValue",
    "SymbolValue",
    "T",
    "TValue",
    "UInt8Value",
    "UInt16Value",
    "UInt32Value",
    "UInt64Value",
    "Value",
]


class Value:
    """A Qy runtime value.

    ``Value`` is the semantic domain faced by all execution backends.  Concrete
    subclasses define language-visible runtime kinds; Python payload classes
    used by one backend are not part of this definition.
    """

    type_name: ClassVar[str] = "value"


class DatumValue(Value):
    """A runtime value that can also be syntax datum."""


@dataclass(frozen=True, slots=True)
class SymbolValue(DatumValue):
    """A runtime symbol value."""

    name: str

    type_name: ClassVar[str] = "symbol"


@dataclass(frozen=True, slots=True)
class NilValue(DatumValue):
    """Qy's unique ``nil`` value.

    ``nil`` is the empty chain and the only false value for core conditional
    semantics.  It is still an atom because only a non-empty chain is non-atom.
    """

    type_name: ClassVar[str] = "nil"


@dataclass(frozen=True, slots=True)
class ChainValue(DatumValue):
    """An immutable non-empty chain cell.

    ``tail`` is a general ``Value`` so improper chains remain representable.
    Proper chains are the subset that eventually end in ``NIL``.
    """

    head: Value
    tail: Value

    type_name: ClassVar[str] = "chain"


@dataclass(frozen=True, slots=True)
class TValue(Value):
    """Qy's unique canonical true value."""

    type_name: ClassVar[str] = "t"


NIL = NilValue()
T = TValue()


_NO_PEER = object()


def _peer_value(other: object) -> object:
    """Extract the underlying Python value for host-level arithmetic.

    Returns ``_NO_PEER`` when *other* is not a host-arithmetic peer.
    """
    if isinstance(other, NumberValue):
        return other.value  # type: ignore[attr-defined]
    if isinstance(other, bool):
        return _NO_PEER
    if isinstance(other, int | float):
        return other
    return _NO_PEER


class ObjectValue(Value):
    """Base class for Qy runtime objects.

    ``number`` and ``string`` are special object families, but they remain
    explicit value kinds because the language gives them dedicated semantics.
    """

    type_name: ClassVar[str] = "object"


class NumberValue(ObjectValue):
    """Base family for numeric values.

    Family membership does not imply substitutability.  Concrete subclasses are
    distinct semantic types, and arithmetic is only defined by declarations that
    explicitly name those concrete types.

    Python-level ``==`` is intentionally permissive: two ``NumberValue``s with
    equal underlying values compare equal regardless of concrete type, and a
    raw Python ``int`` / ``float`` compares equal to a ``NumberValue`` with the
    same value. This is a host-level convenience for tests / debug output and
    does *not* affect Qy semantics — Qy's ``=`` operator does its own
    same-concrete-type check via ``_num_eq``.
    """

    type_name: ClassVar[str] = "number"
    exact: ClassVar[bool]
    fixed_width: ClassVar[bool]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, NumberValue):
            return self.value == other.value  # type: ignore[attr-defined]
        if isinstance(other, bool):
            return False
        if isinstance(other, int | float):
            return self.value == other  # type: ignore[attr-defined]
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("qy-number", self.value))  # type: ignore[attr-defined]

    def __int__(self) -> int:
        return int(self.value)  # type: ignore[attr-defined]

    def __float__(self) -> float:
        return float(self.value)  # type: ignore[attr-defined]

    def __index__(self) -> int:
        v = self.value  # type: ignore[attr-defined]
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        raise TypeError(f"{type(self).__name__} cannot be used as an index")

    def __str__(self) -> str:
        return str(self.value)  # type: ignore[attr-defined]

    def __format__(self, spec: str) -> str:
        return format(self.value, spec)  # type: ignore[attr-defined]

    def __bool__(self) -> bool:
        return bool(self.value)  # type: ignore[attr-defined]

    # Python-level numeric protocol. These are *host adapters* — they let
    # idiomatic Python code (host operators, debug formatters, sequence
    # indexing) treat ``NumberValue`` like its underlying Python value. They
    # do not affect Qy semantics: the language's ``+``/``-``/``*``/``/`` go
    # through ``qy.std.arithmetic`` and require concrete-type consistency.
    def __add__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value + v  # type: ignore[attr-defined]

    def __radd__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else v + self.value  # type: ignore[attr-defined]

    def __sub__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value - v  # type: ignore[attr-defined]

    def __rsub__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else v - self.value  # type: ignore[attr-defined]

    def __mul__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value * v  # type: ignore[attr-defined]

    def __rmul__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else v * self.value  # type: ignore[attr-defined]

    def __truediv__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value / v  # type: ignore[attr-defined]

    def __rtruediv__(self, other: object) -> object:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else v / self.value  # type: ignore[attr-defined]

    def __neg__(self) -> object:
        return -self.value  # type: ignore[attr-defined]

    def __pos__(self) -> object:
        return +self.value  # type: ignore[attr-defined]

    def __lt__(self, other: object) -> bool:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value < v  # type: ignore[attr-defined,return-value]

    def __le__(self, other: object) -> bool:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value <= v  # type: ignore[attr-defined,return-value]

    def __gt__(self, other: object) -> bool:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value > v  # type: ignore[attr-defined,return-value]

    def __ge__(self, other: object) -> bool:
        v = _peer_value(other)
        return NotImplemented if v is _NO_PEER else self.value >= v  # type: ignore[attr-defined,return-value]


class IntegerValue(NumberValue):
    """Base family for integer values."""

    exact: ClassVar[bool] = True


@dataclass(frozen=True, slots=True, eq=False)
class IntValue(IntegerValue):
    """Arbitrary-precision integer value."""

    value: int

    type_name: ClassVar[str] = "int"
    fixed_width: ClassVar[bool] = False


@dataclass(frozen=True, slots=True, eq=False)
class Int32Value(IntegerValue):
    """Signed 32-bit integer value."""

    value: int

    type_name: ClassVar[str] = "int32"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = -(2**31)
    max_value: ClassVar[int] = 2**31 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class Int64Value(IntegerValue):
    """Signed 64-bit integer value."""

    value: int

    type_name: ClassVar[str] = "int64"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = -(2**63)
    max_value: ClassVar[int] = 2**63 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class Int8Value(IntegerValue):
    """Signed 8-bit integer value."""

    value: int

    type_name: ClassVar[str] = "int8"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = -(2**7)
    max_value: ClassVar[int] = 2**7 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class Int16Value(IntegerValue):
    """Signed 16-bit integer value."""

    value: int

    type_name: ClassVar[str] = "int16"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = -(2**15)
    max_value: ClassVar[int] = 2**15 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class UInt8Value(IntegerValue):
    """Unsigned 8-bit integer value."""

    value: int

    type_name: ClassVar[str] = "uint8"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = 0
    max_value: ClassVar[int] = 2**8 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class UInt16Value(IntegerValue):
    """Unsigned 16-bit integer value."""

    value: int

    type_name: ClassVar[str] = "uint16"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = 0
    max_value: ClassVar[int] = 2**16 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class UInt32Value(IntegerValue):
    """Unsigned 32-bit integer value."""

    value: int

    type_name: ClassVar[str] = "uint32"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = 0
    max_value: ClassVar[int] = 2**32 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class UInt64Value(IntegerValue):
    """Unsigned 64-bit integer value."""

    value: int

    type_name: ClassVar[str] = "uint64"
    fixed_width: ClassVar[bool] = True
    min_value: ClassVar[int] = 0
    max_value: ClassVar[int] = 2**64 - 1

    def __post_init__(self) -> None:
        _require_range(self.value, self.min_value, self.max_value, self.type_name)


@dataclass(frozen=True, slots=True, eq=False)
class FloatValue(NumberValue):
    """IEEE 754 binary64 floating-point value."""

    value: float

    type_name: ClassVar[str] = "float"
    exact: ClassVar[bool] = False
    fixed_width: ClassVar[bool] = True
    width_bits: ClassVar[int] = 64


@dataclass(frozen=True, slots=True, eq=False)
class Float32Value(NumberValue):
    """IEEE 754 binary32 floating-point value."""

    value: float

    type_name: ClassVar[str] = "float32"
    exact: ClassVar[bool] = False
    fixed_width: ClassVar[bool] = True
    width_bits: ClassVar[int] = 32


@dataclass(frozen=True, slots=True, eq=False)
class Float16Value(NumberValue):
    """IEEE 754 binary16 floating-point value (half precision)."""

    value: float

    type_name: ClassVar[str] = "float16"
    exact: ClassVar[bool] = False
    fixed_width: ClassVar[bool] = True
    width_bits: ClassVar[int] = 16


# Float64Value is an alias for FloatValue (both are IEEE 754 binary64)
Float64Value = FloatValue


@dataclass(frozen=True, slots=True, eq=False)
class Float128Value(NumberValue):
    """IEEE 754 binary128 floating-point value (quadruple precision).

    Note: Python's native float is binary64. This type defines the semantic
    model for float128, but the Python VM approximates it using float.
    """

    value: float

    type_name: ClassVar[str] = "float128"
    exact: ClassVar[bool] = False
    fixed_width: ClassVar[bool] = True
    width_bits: ClassVar[int] = 128


@dataclass(frozen=True, slots=True, eq=False)
class ComplexValue(NumberValue):
    """Complex number with binary64 real and imaginary parts."""

    real: FloatValue
    imag: FloatValue

    type_name: ClassVar[str] = "complex"
    exact: ClassVar[bool] = False
    fixed_width: ClassVar[bool] = True


@dataclass(frozen=True, slots=True, eq=False)
class RationalValue(NumberValue):
    """Exact rational number made from arbitrary-precision integers."""

    numerator: IntValue
    denominator: IntValue

    type_name: ClassVar[str] = "rational"
    exact: ClassVar[bool] = True
    fixed_width: ClassVar[bool] = False

    def __post_init__(self) -> None:
        if self.denominator.value == 0:
            raise ValueError("rational denominator must not be zero")


@dataclass(frozen=True, slots=True)
class CharValue(ObjectValue):
    """A single Unicode scalar value."""

    value: str

    type_name: ClassVar[str] = "char"

    def __post_init__(self) -> None:
        if len(self.value) != 1:
            raise ValueError("char value must contain exactly one Unicode scalar")


@dataclass(frozen=True, slots=True)
class StringValue(ObjectValue):
    """Qy runtime string value.

    Strings are first-class runtime values, not host ``str`` references.  A
    backend may choose a contiguous character/byte layout, but the semantic
    value remains ``string`` rather than ``array[char]``.
    """

    value: str

    type_name: ClassVar[str] = "string"


@dataclass(slots=True)
class ArrayValue(ObjectValue):
    """A contiguous runtime memory segment.

    ``array`` is a low-level object family.  Higher-level mutable lists,
    immutable tuples, typed buffers, and similar library objects can build on
    top of it, but they are not aliases of ``array`` itself.

    ``element_type`` is either:

    - ``Value`` for a generic boxed segment of Qy value cells;
    - one concrete value type for a specialized segment.

    Family membership is not enough here: ``array[int32]`` and
    ``array[int64]`` have different element layouts, and an ``Int64Value``
    cannot be silently inserted into an ``array[Int32Value]``.
    """

    element_type: type[Value]
    items: list[Value]

    type_name: ClassVar[str] = "array"
    contiguous: ClassVar[bool] = True

    def __post_init__(self) -> None:
        _require_array_element_type(self.element_type)
        for item in self.items:
            _require_array_element_value(item, self.element_type)

    @property
    def length(self) -> int:
        return len(self.items)


@dataclass(slots=True)
class HashMapValue(ObjectValue):
    """A hash-map object family value.

    The semantic model stores entries as key/value pairs rather than reusing a
    Python ``dict`` so Qy's future hash/equality rules stay independent from the
    host runtime.  The later hash/equality declaration will define when entries
    conflict or replace each other.  User-facing ``dict`` can be a standard
    object built on top of this family.
    """

    entries: list[tuple[Value, Value]]

    type_name: ClassVar[str] = "hash-map"

    @property
    def length(self) -> int:
        return len(self.entries)


def _require_range(value: int, minimum: int, maximum: int, type_name: str) -> None:
    if not minimum <= value <= maximum:
        raise ValueError(f"{type_name} value out of range: {value}")


def _require_array_element_type(value_type: type[Value]) -> None:
    if value_type is Value:
        return
    if value_type in {
        DatumValue,
        ObjectValue,
        NumberValue,
        IntegerValue,
    }:
        raise ValueError(
            f"array element_type must be Value or a concrete Value type, got {value_type.__name__}"
        )


def _require_array_element_value(value: Value, expected: type[Value]) -> None:
    if expected is Value:
        if not isinstance(value, Value):
            raise TypeError(f"array element expects Value, got {type(value).__name__}")
        return
    if type(value) is not expected:
        raise TypeError(f"array element expects {expected.__name__}, got {type(value).__name__}")
