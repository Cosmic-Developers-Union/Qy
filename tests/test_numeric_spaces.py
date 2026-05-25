# coding: utf-8
"""Tests for hardware numeric symbol spaces."""

import pytest

from qy.core.syntax import nil as QY_NIL
from qy.errors import QyEffectSignal
from qy.errors import QyTypeError
from qy.frontend.reader import Symbol
from qy.sem.core import Int32Value
from qy.sem.core import IntValue
from qy.sem.core import T as QY_T
from qy.sem.core import UInt8Value
from qy.std.numeric_spaces import make_int32_space
from qy.std.numeric_spaces import make_uint8_space

S = Symbol


class TestInt32Space:
    """Test qy.int32 hardware space."""

    def test_module_structure(self):
        """Test int32 module exports correct symbols."""
        module = make_int32_space()
        assert module.name == "qy.int32"

        # Check key exports exist
        assert S("int32") in module.exports
        assert S("int32?") in module.exports
        assert S("+") in module.exports
        assert S("-") in module.exports
        assert S("*") in module.exports
        assert S("/") in module.exports
        assert S("mod") in module.exports
        assert S("<") in module.exports
        assert S("=") in module.exports
        assert S("bit-and") in module.exports
        assert S("min-value") in module.exports
        assert S("max-value") in module.exports
        assert S("bits") in module.exports

    def test_constructor_from_int_value(self):
        """Test int32 constructor from IntValue."""
        module = make_int32_space()
        constructor = module.exports[S("int32")]

        result = constructor.func(IntValue(42))
        assert isinstance(result, Int32Value)
        assert result.value == 42

    def test_constructor_from_raw_int(self):
        """Test int32 constructor from raw Python int."""
        module = make_int32_space()
        constructor = module.exports[S("int32")]

        result = constructor.func(100)
        assert isinstance(result, Int32Value)
        assert result.value == 100

    def test_constructor_overflow(self):
        """Test int32 constructor raises effect on overflow."""
        module = make_int32_space()
        constructor = module.exports[S("int32")]

        with pytest.raises(QyEffectSignal) as exc_info:
            constructor.func(IntValue(2**31))

        assert exc_info.value.effect == "numeric-overflow"
        assert exc_info.value.arg["type"] == "int32"

    def test_type_predicate(self):
        """Test int32? type predicate."""
        module = make_int32_space()
        predicate = module.exports[S("int32?")]

        assert predicate.func(Int32Value(42)) is QY_T
        assert predicate.func(IntValue(42)) is QY_NIL
        assert predicate.func(42) is QY_NIL

    def test_addition(self):
        """Test typed addition."""
        module = make_int32_space()
        add = module.exports[S("+")]

        result = add.func(Int32Value(10), Int32Value(20))
        assert isinstance(result, Int32Value)
        assert result.value == 30

    def test_addition_overflow(self):
        """Test addition overflow raises effect."""
        module = make_int32_space()
        add = module.exports[S("+")]

        with pytest.raises(QyEffectSignal) as exc_info:
            add.func(Int32Value(2**31 - 1), Int32Value(1))

        assert exc_info.value.effect == "numeric-overflow"

    def test_addition_type_mismatch(self):
        """Test addition rejects wrong types."""
        module = make_int32_space()
        add = module.exports[S("+")]

        with pytest.raises(QyTypeError) as exc_info:
            add.func(Int32Value(10), IntValue(20))

        assert "expects int32" in str(exc_info.value)

    def test_subtraction(self):
        """Test typed subtraction."""
        module = make_int32_space()
        sub = module.exports[S("-")]

        result = sub.func(Int32Value(50), Int32Value(20))
        assert isinstance(result, Int32Value)
        assert result.value == 30

    def test_negation(self):
        """Test unary negation."""
        module = make_int32_space()
        sub = module.exports[S("-")]

        result = sub.func(Int32Value(42))
        assert isinstance(result, Int32Value)
        assert result.value == -42

    def test_multiplication(self):
        """Test typed multiplication."""
        module = make_int32_space()
        mul = module.exports[S("*")]

        result = mul.func(Int32Value(6), Int32Value(7))
        assert isinstance(result, Int32Value)
        assert result.value == 42

    def test_division(self):
        """Test typed integer division."""
        module = make_int32_space()
        div = module.exports[S("/")]

        result = div.func(Int32Value(42), Int32Value(6))
        assert isinstance(result, Int32Value)
        assert result.value == 7

    def test_division_by_zero(self):
        """Test division by zero raises effect."""
        module = make_int32_space()
        div = module.exports[S("/")]

        with pytest.raises(QyEffectSignal) as exc_info:
            div.func(Int32Value(42), Int32Value(0))

        assert exc_info.value.effect == "divide-by-zero"

    def test_modulus(self):
        """Test modulus operation."""
        module = make_int32_space()
        mod = module.exports[S("mod")]

        result = mod.func(Int32Value(17), Int32Value(5))
        assert isinstance(result, Int32Value)
        assert result.value == 2

    def test_comparison_less_than(self):
        """Test less than comparison."""
        module = make_int32_space()
        lt = module.exports[S("<")]

        assert lt.func(Int32Value(10), Int32Value(20)) is QY_T
        assert lt.func(Int32Value(20), Int32Value(10)) is QY_NIL
        assert lt.func(Int32Value(10), Int32Value(10)) is QY_NIL

    def test_comparison_greater_than(self):
        """Test greater than comparison."""
        module = make_int32_space()
        gt = module.exports[S(">")]

        assert gt.func(Int32Value(20), Int32Value(10)) is QY_T
        assert gt.func(Int32Value(10), Int32Value(20)) is QY_NIL

    def test_equality(self):
        """Test typed equality."""
        module = make_int32_space()
        eq = module.exports[S("=")]

        assert eq.func(Int32Value(42), Int32Value(42)) is QY_T
        assert eq.func(Int32Value(42), Int32Value(43)) is QY_NIL
        # Different types are not equal
        assert eq.func(Int32Value(42), IntValue(42)) is QY_NIL

    def test_bitwise_and(self):
        """Test bitwise AND."""
        module = make_int32_space()
        bit_and = module.exports[S("bit-and")]

        result = bit_and.func(Int32Value(0b1100), Int32Value(0b1010))
        assert isinstance(result, Int32Value)
        assert result.value == 0b1000

    def test_bitwise_or(self):
        """Test bitwise OR."""
        module = make_int32_space()
        bit_or = module.exports[S("bit-or")]

        result = bit_or.func(Int32Value(0b1100), Int32Value(0b1010))
        assert isinstance(result, Int32Value)
        assert result.value == 0b1110

    def test_bitwise_xor(self):
        """Test bitwise XOR."""
        module = make_int32_space()
        bit_xor = module.exports[S("bit-xor")]

        result = bit_xor.func(Int32Value(0b1100), Int32Value(0b1010))
        assert isinstance(result, Int32Value)
        assert result.value == 0b0110

    def test_bitwise_not(self):
        """Test bitwise NOT."""
        module = make_int32_space()
        bit_not = module.exports[S("bit-not")]

        result = bit_not.func(Int32Value(0))
        assert isinstance(result, Int32Value)
        assert result.value == -1

    def test_shift_left(self):
        """Test left shift."""
        module = make_int32_space()
        shl = module.exports[S("shl")]

        result = shl.func(Int32Value(1), 3)
        assert isinstance(result, Int32Value)
        assert result.value == 8

    def test_shift_right(self):
        """Test right shift."""
        module = make_int32_space()
        shr = module.exports[S("shr")]

        result = shr.func(Int32Value(16), 2)
        assert isinstance(result, Int32Value)
        assert result.value == 4

    def test_constants(self):
        """Test min-value, max-value, bits constants."""
        module = make_int32_space()

        min_val = module.exports[S("min-value")]
        max_val = module.exports[S("max-value")]
        bits = module.exports[S("bits")]

        assert isinstance(min_val, Int32Value)
        assert min_val.value == -(2**31)

        assert isinstance(max_val, Int32Value)
        assert max_val.value == 2**31 - 1

        assert isinstance(bits, IntValue)
        assert bits.value == 32


class TestUInt8Space:
    """Test qy.uint8 hardware space."""

    def test_constructor_valid_range(self):
        """Test uint8 constructor accepts valid range."""
        module = make_uint8_space()
        constructor = module.exports[S("uint8")]

        result = constructor.func(IntValue(255))
        assert isinstance(result, UInt8Value)
        assert result.value == 255

    def test_constructor_rejects_negative(self):
        """Test uint8 constructor rejects negative values."""
        module = make_uint8_space()
        constructor = module.exports[S("uint8")]

        with pytest.raises(QyEffectSignal) as exc_info:
            constructor.func(IntValue(-1))

        assert exc_info.value.effect == "numeric-overflow"

    def test_addition(self):
        """Test uint8 addition."""
        module = make_uint8_space()
        add = module.exports[S("+")]

        result = add.func(UInt8Value(100), UInt8Value(50))
        assert isinstance(result, UInt8Value)
        assert result.value == 150

    def test_addition_overflow(self):
        """Test uint8 addition overflow."""
        module = make_uint8_space()
        add = module.exports[S("+")]

        with pytest.raises(QyEffectSignal) as exc_info:
            add.func(UInt8Value(200), UInt8Value(100))

        assert exc_info.value.effect == "numeric-overflow"

    def test_constants(self):
        """Test uint8 constants."""
        module = make_uint8_space()

        min_val = module.exports[S("min-value")]
        max_val = module.exports[S("max-value")]
        bits = module.exports[S("bits")]

        assert isinstance(min_val, UInt8Value)
        assert min_val.value == 0

        assert isinstance(max_val, UInt8Value)
        assert max_val.value == 255

        assert isinstance(bits, IntValue)
        assert bits.value == 8
