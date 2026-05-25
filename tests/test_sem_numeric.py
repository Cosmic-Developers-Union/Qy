# coding: utf-8
"""Tests for semantic numeric value types."""

import pytest

from qy.sem.core import Float16Value
from qy.sem.core import Float32Value
from qy.sem.core import Float64Value
from qy.sem.core import Float128Value
from qy.sem.core import FloatValue
from qy.sem.core import Int8Value
from qy.sem.core import Int16Value
from qy.sem.core import Int32Value
from qy.sem.core import Int64Value
from qy.sem.core import IntValue
from qy.sem.core import UInt8Value
from qy.sem.core import UInt16Value
from qy.sem.core import UInt32Value
from qy.sem.core import UInt64Value


class TestIntegerValues:
    """Test integer value types."""

    def test_int_value_arbitrary_precision(self):
        """Test IntValue supports arbitrary precision."""
        large = IntValue(2**100)
        assert large.value == 2**100
        assert large.type_name == "int"
        assert not large.fixed_width
        assert large.exact

    def test_int8_value_valid_range(self):
        """Test Int8Value accepts valid range."""
        min_val = Int8Value(-128)
        max_val = Int8Value(127)
        zero = Int8Value(0)

        assert min_val.value == -128
        assert max_val.value == 127
        assert zero.value == 0
        assert min_val.type_name == "int8"
        assert min_val.fixed_width
        assert min_val.exact

    def test_int8_value_rejects_out_of_range(self):
        """Test Int8Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="int8 value out of range"):
            Int8Value(-129)
        with pytest.raises(ValueError, match="int8 value out of range"):
            Int8Value(128)

    def test_int16_value_valid_range(self):
        """Test Int16Value accepts valid range."""
        min_val = Int16Value(-32768)
        max_val = Int16Value(32767)

        assert min_val.value == -32768
        assert max_val.value == 32767
        assert min_val.type_name == "int16"

    def test_int16_value_rejects_out_of_range(self):
        """Test Int16Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="int16 value out of range"):
            Int16Value(-32769)
        with pytest.raises(ValueError, match="int16 value out of range"):
            Int16Value(32768)

    def test_int32_value_valid_range(self):
        """Test Int32Value accepts valid range."""
        min_val = Int32Value(-(2**31))
        max_val = Int32Value(2**31 - 1)

        assert min_val.value == -(2**31)
        assert max_val.value == 2**31 - 1
        assert min_val.type_name == "int32"

    def test_int32_value_rejects_out_of_range(self):
        """Test Int32Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="int32 value out of range"):
            Int32Value(-(2**31) - 1)
        with pytest.raises(ValueError, match="int32 value out of range"):
            Int32Value(2**31)

    def test_int64_value_valid_range(self):
        """Test Int64Value accepts valid range."""
        min_val = Int64Value(-(2**63))
        max_val = Int64Value(2**63 - 1)

        assert min_val.value == -(2**63)
        assert max_val.value == 2**63 - 1
        assert min_val.type_name == "int64"

    def test_int64_value_rejects_out_of_range(self):
        """Test Int64Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="int64 value out of range"):
            Int64Value(-(2**63) - 1)
        with pytest.raises(ValueError, match="int64 value out of range"):
            Int64Value(2**63)

    def test_uint8_value_valid_range(self):
        """Test UInt8Value accepts valid range."""
        min_val = UInt8Value(0)
        max_val = UInt8Value(255)

        assert min_val.value == 0
        assert max_val.value == 255
        assert min_val.type_name == "uint8"

    def test_uint8_value_rejects_out_of_range(self):
        """Test UInt8Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="uint8 value out of range"):
            UInt8Value(-1)
        with pytest.raises(ValueError, match="uint8 value out of range"):
            UInt8Value(256)

    def test_uint16_value_valid_range(self):
        """Test UInt16Value accepts valid range."""
        min_val = UInt16Value(0)
        max_val = UInt16Value(65535)

        assert min_val.value == 0
        assert max_val.value == 65535
        assert min_val.type_name == "uint16"

    def test_uint16_value_rejects_out_of_range(self):
        """Test UInt16Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="uint16 value out of range"):
            UInt16Value(-1)
        with pytest.raises(ValueError, match="uint16 value out of range"):
            UInt16Value(65536)

    def test_uint32_value_valid_range(self):
        """Test UInt32Value accepts valid range."""
        min_val = UInt32Value(0)
        max_val = UInt32Value(2**32 - 1)

        assert min_val.value == 0
        assert max_val.value == 2**32 - 1
        assert min_val.type_name == "uint32"

    def test_uint32_value_rejects_out_of_range(self):
        """Test UInt32Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="uint32 value out of range"):
            UInt32Value(-1)
        with pytest.raises(ValueError, match="uint32 value out of range"):
            UInt32Value(2**32)

    def test_uint64_value_valid_range(self):
        """Test UInt64Value accepts valid range."""
        min_val = UInt64Value(0)
        max_val = UInt64Value(2**64 - 1)

        assert min_val.value == 0
        assert max_val.value == 2**64 - 1
        assert min_val.type_name == "uint64"

    def test_uint64_value_rejects_out_of_range(self):
        """Test UInt64Value rejects out-of-range values."""
        with pytest.raises(ValueError, match="uint64 value out of range"):
            UInt64Value(-1)
        with pytest.raises(ValueError, match="uint64 value out of range"):
            UInt64Value(2**64)


class TestFloatValues:
    """Test floating-point value types."""

    def test_float_value_is_float64(self):
        """Test FloatValue is IEEE 754 binary64."""
        val = FloatValue(3.14)
        assert val.value == 3.14
        assert val.type_name == "float"
        assert val.width_bits == 64
        assert not val.exact
        assert val.fixed_width

    def test_float64_value_is_alias(self):
        """Test Float64Value is an alias for FloatValue."""
        assert Float64Value is FloatValue

    def test_float16_value(self):
        """Test Float16Value."""
        val = Float16Value(1.5)
        assert val.value == 1.5
        assert val.type_name == "float16"
        assert val.width_bits == 16
        assert not val.exact
        assert val.fixed_width

    def test_float32_value(self):
        """Test Float32Value."""
        val = Float32Value(2.5)
        assert val.value == 2.5
        assert val.type_name == "float32"
        assert val.width_bits == 32
        assert not val.exact
        assert val.fixed_width

    def test_float128_value(self):
        """Test Float128Value."""
        val = Float128Value(1.23456789)
        assert val.value == 1.23456789
        assert val.type_name == "float128"
        assert val.width_bits == 128
        assert not val.exact
        assert val.fixed_width


class TestValueImmutability:
    """Test that value types are immutable."""

    def test_int_value_frozen(self):
        """Test IntValue is frozen."""
        val = IntValue(42)
        with pytest.raises(AttributeError):
            val.value = 100  # type: ignore

    def test_int32_value_frozen(self):
        """Test Int32Value is frozen."""
        val = Int32Value(42)
        with pytest.raises(AttributeError):
            val.value = 100  # type: ignore

    def test_float_value_frozen(self):
        """Test FloatValue is frozen."""
        val = FloatValue(3.14)
        with pytest.raises(AttributeError):
            val.value = 2.71  # type: ignore
