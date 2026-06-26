# coding: utf-8
"""Tests for pre-symbol-space implementation."""

import pytest

from qy.core.symbol_space import MISSING as _MISSING
from qy.core.symbol_space import SymbolSpace
from qy.core.syntax import nil as QY_NIL
from qy.errors import QyResolveError
from qy.frontend.reader import Symbol
from qy.sem.core import T as QY_T
from qy.session.pre_ss import create_lisp_ss
from qy.session.pre_ss import create_literal_ss
from qy.session.pre_ss import create_number_ss
from qy.session.pre_ss import create_pre_ssc
from qy.session.pre_ss import create_string_ss
from qy.session.pre_ss import create_value_ss
from qy.session.pre_ss import is_number_literal
from qy.session.pre_ss import is_string_literal
from qy.session.pre_ss import parse_number_literal
from qy.session.pre_ss import parse_string_literal

S = Symbol


def test_is_string_literal():
    """Test string literal detection."""
    assert is_string_literal('"hello"')
    assert is_string_literal('r"raw"')
    assert not is_string_literal("hello")
    assert not is_string_literal("123")


def test_parse_string_literal():
    """Test string literal parsing."""
    assert parse_string_literal('"hello"') == "hello"
    assert parse_string_literal('"hello\\nworld"') == "hello\nworld"
    assert parse_string_literal('r"raw\\n"') == "raw\\n"
    assert parse_string_literal('"invalid') is _MISSING
    assert parse_string_literal("not-a-string") is _MISSING


def test_is_number_literal():
    """Test number literal detection."""
    assert is_number_literal("123")
    assert is_number_literal("-456")
    assert is_number_literal("3.14")
    assert is_number_literal("-2.5")
    assert not is_number_literal("hello")
    assert not is_number_literal('"123"')


def test_parse_number_literal():
    """Test number literal parsing returns semantic values."""
    from qy.sem.core import FloatValue
    from qy.sem.core import IntValue

    result_int = parse_number_literal("123")
    assert isinstance(result_int, IntValue)
    assert result_int.value == 123

    result_neg = parse_number_literal("-456")
    assert isinstance(result_neg, IntValue)
    assert result_neg.value == -456

    result_float = parse_number_literal("3.14")
    assert isinstance(result_float, FloatValue)
    assert result_float.value == 3.14

    result_neg_float = parse_number_literal("-2.5")
    assert isinstance(result_neg_float, FloatValue)
    assert result_neg_float.value == -2.5

    assert parse_number_literal("hello") is _MISSING


def test_create_lisp_ss():
    """Test lisp-ss creation."""
    from qy.sem.core import NONE as QY_NONE

    lisp = create_lisp_ss()

    assert lisp.name == "lisp-ss"
    assert not lisp.writable
    assert lisp.lookup(S("T")) is QY_T
    assert lisp.lookup(S("nil")) is QY_NIL
    assert lisp.lookup(S("true")) is QY_T
    assert lisp.lookup(S("false")) is QY_NIL
    assert lisp.lookup(S("none")) is QY_NONE
    assert lisp.lookup(S("undefined")) is _MISSING


def test_create_number_ss():
    """Test number-ss creation."""
    number = create_number_ss()

    assert number.name == "number-ss"
    assert not number.writable
    assert number.parent is None


def test_number_ss_holds_operators_and_literals():
    """number-ss 同时持有数字算子 (有限部分) 与数字字面量识别 (无限部分)。.

    这是 Phase 2 的核心契约: ``+ - * / = < > <= >= mod`` 直接绑定在 number-ss
    内, 与 ``42`` / ``-3`` / ``2.5`` 这类字面量并列。``(+ 1 2)`` 在 ssc 上找
    ``+`` 与 ``1`` ``2`` 时, 命中同一个空间。
    """
    from qy.core.operators import PureOperator
    from qy.core.symbol_space import MISSING
    from qy.sem.core import FloatValue
    from qy.sem.core import IntValue

    number = create_number_ss()

    # 算子 (有限部分)
    for op in ("+", "-", "*", "/", "=", "==", "<", ">", "<=", ">=", "mod"):
        assert number.contains(S(op)), f"{op!r} should be in number-ss"
        binding = number.lookup(S(op))
        assert isinstance(binding, PureOperator), f"{op!r} should be PureOperator"

    # 字面量 (无限部分)
    assert number.contains(S("42"))
    assert number.lookup(S("42")) == IntValue(42)
    assert number.contains(S("-3"))
    assert number.lookup(S("-3")) == IntValue(-3)
    assert number.contains(S("2.5"))
    assert number.lookup(S("2.5")) == FloatValue(2.5)

    # 非数字非算子: MISSING
    assert not number.contains(S("foo"))
    assert number.lookup(S("foo")) is MISSING


def test_create_string_ss():
    """Test string-ss creation."""
    string = create_string_ss()

    assert string.name == "string-ss"
    assert not string.writable
    assert string.parent is None


def test_create_value_ss():
    """Test value-ss creation: returns the head of the number/char/string-ss chain."""
    value = create_value_ss()

    # value-ss is now a three-layer chain whose head is string-ss.
    assert value.name == "string-ss"
    assert not value.writable


def test_create_literal_ss():
    """Test literal-ss creation with all literal types."""
    literal = create_literal_ss()

    # literal-ss exposes the head of the value-ss chain (string-ss).
    assert literal.name == "string-ss"
    assert not literal.writable
    # Should have lisp-ss in parent chain (chain lookup via resolve)
    assert literal.resolve(S("T")) is QY_T
    assert literal.resolve(S("nil")) is QY_NIL


def test_create_pre_ssc_without_stdlib():
    """Test pre-ssc creation without stdlib."""
    pre_ssc = create_pre_ssc()

    assert pre_ssc.name == "pre-ssc-head"
    assert pre_ssc.writable
    # Should have lisp-ss in parent chain
    assert pre_ssc.resolve(S("T")) is QY_T
    assert pre_ssc.resolve(S("nil")) is QY_NIL


def test_create_pre_ssc_with_stdlib():
    """Test pre-ssc creation with stdlib."""
    stdlib = SymbolSpace({S("foo"): "bar"}, name="test-stdlib")
    pre_ssc = create_pre_ssc(stdlib)

    assert pre_ssc.name == "pre-ssc-head"
    assert pre_ssc.writable
    # Should have both lisp-ss and stdlib in parent chain
    assert pre_ssc.resolve(S("T")) is QY_T
    assert pre_ssc.resolve(S("foo")) == "bar"


def test_resolve_literal_in_pre_ss_lisp_values():
    """Test resolving Lisp values through pre-ss (chain walk via resolve)."""
    from qy.sem.core import NONE as QY_NONE

    pre_ss = create_pre_ssc()

    assert pre_ss.resolve(S("T")) is QY_T
    assert pre_ss.resolve(S("nil")) is QY_NIL
    assert pre_ss.resolve(S("true")) is QY_T
    assert pre_ss.resolve(S("false")) is QY_NIL
    assert pre_ss.resolve(S("none")) is QY_NONE


def test_resolve_literal_in_pre_ss_numbers():
    """Test resolving number literals through pre-ss returns semantic values."""
    from qy.sem.core import FloatValue
    from qy.sem.core import IntValue

    pre_ss = create_pre_ssc()

    result_int = pre_ss.resolve(S("123"))
    assert isinstance(result_int, IntValue)
    assert result_int.value == 123

    result_neg = pre_ss.resolve(S("-456"))
    assert isinstance(result_neg, IntValue)
    assert result_neg.value == -456

    result_float = pre_ss.resolve(S("3.14"))
    assert isinstance(result_float, FloatValue)
    assert result_float.value == 3.14

    result_neg_float = pre_ss.resolve(S("-2.5"))
    assert isinstance(result_neg_float, FloatValue)
    assert result_neg_float.value == -2.5


def test_resolve_literal_in_pre_ss_strings():
    """Test resolving string literals through pre-ss."""
    pre_ss = create_pre_ssc()

    assert pre_ss.resolve(S('"hello"')) == "hello"
    assert pre_ss.resolve(S('"world\\n"')) == "world\n"
    assert pre_ss.resolve(S('r"raw\\n"')) == "raw\\n"


def test_resolve_literal_in_pre_ss_undefined():
    """Test resolving undefined symbols returns MISSING."""
    pre_ss = create_pre_ssc()

    assert pre_ss.resolve(S("undefined")) is _MISSING
    assert pre_ss.resolve(S("not-a-literal")) is _MISSING


def test_resolve_literal_in_pre_ss_with_user_bindings():
    """Test that user bindings in pre-ss take precedence."""
    pre_ss = create_pre_ssc()
    pre_ss.define(S("custom"), "custom-value")

    assert pre_ss.resolve(S("custom")) == "custom-value"


def test_lisp_ss_immutable():
    """Test that lisp-ss is immutable (writable=False)."""
    lisp = create_lisp_ss()

    assert not lisp.writable
    # Can still define (writable controls semantic intent, not enforcement)
    # but the flag indicates it should not be modified


def test_pre_ssc_chain_structure():
    """Test the structure of pre-ssc chain."""
    stdlib = SymbolSpace({S("stdlib-sym"): "stdlib-val"}, name="stdlib")
    pre_ssc = create_pre_ssc(stdlib)

    # Check chain structure
    frames = pre_ssc.chain().frames()
    frame_names = [f.name for f in frames]

    # Should have: lisp-ss -> number-ss -> char-ss -> string-ss -> stdlib -> pre-ssc-head
    assert "lisp-ss" in frame_names
    assert "number-ss" in frame_names
    assert "char-ss" in frame_names
    assert "string-ss" in frame_names
    assert "stdlib" in frame_names
    assert "pre-ssc-head" in frame_names


def test_literal_ss_with_parent():
    """Test literal-ss creation with custom parent."""
    parent = SymbolSpace({S("parent-sym"): "parent-val"}, name="parent")
    literal = create_literal_ss(parent=parent)

    # Should be able to look up parent symbols (chain lookup)
    assert literal.resolve(S("parent-sym")) == "parent-val"
    # And lisp symbols
    assert literal.resolve(S("T")) is QY_T


def test_number_ss_with_parent():
    """Test number-ss creation with parent."""
    parent = SymbolSpace({S("x"): 10}, name="parent")
    number = create_number_ss(parent=parent)

    assert number.parent is parent
    assert number.resolve(S("x")) == 10


def test_string_ss_with_parent():
    """Test string-ss creation with parent."""
    parent = SymbolSpace({S("x"): 10}, name="parent")
    string = create_string_ss(parent=parent)

    assert string.parent is parent
    assert string.resolve(S("x")) == 10


def test_value_ss_with_parent():
    """Test value-ss creation with parent: parent reachable through chain."""
    parent = SymbolSpace({S("x"): 10}, name="parent")
    value = create_value_ss(parent=parent)

    # value-ss is now a 3-layer chain; its tail (number-ss) parents `parent`.
    assert value.resolve(S("x")) == 10


def test_resolve_literal_priority():
    """Test that symbol-space bindings take priority over literal parsing."""
    pre_ss = create_pre_ssc()
    # Define a symbol that looks like a number
    pre_ss.define(S("123"), "not-a-number")

    # Should return the binding, not parse as number
    assert pre_ss.resolve(S("123")) == "not-a-number"


def test_profile_config_with_pre_ss():
    """ProfileConfig 不再持有内建 pre-ssc; 字面量解析由 standard-space 的 ssc walk 完成。.

    profile.resolve_literal 仅作为 ssc miss 后的 escape hatch。这里通过
    create_standard_space() 拿到完整 pre-ssc 来验证字面量解析。
    """
    from qy.sem.core import IntValue
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig()
    space = profile.create_standard_space()

    assert space.resolve(S("T")) is QY_T
    assert space.resolve(S("nil")) is QY_NIL
    assert space.resolve(S("123")) == IntValue(123)
    assert space.resolve(S('"hello"')) == "hello"

    # profile.resolve_literal alone (without space) raises for any symbol.
    with pytest.raises(QyResolveError) as exc_info:
        profile.resolve_literal(S("undefined"))
    assert "unresolved symbol" in str(exc_info.value)


def test_profile_config_user_literal_resolver_hook():
    """User-supplied literal_resolver runs after ssc miss as escape hatch."""
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig(literal_resolver=lambda s: f"resolved-{s.name}")
    assert profile.resolve_literal(S("anything")) == "resolved-anything"


def test_profile_config_create_standard_space_with_pre_ss():
    """Test creating standard space integrates pre-ssc."""
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig()
    space = profile.create_standard_space()

    # Should have lisp values (chain lookup via resolve)
    assert space.resolve(S("T")) is QY_T
    assert space.resolve(S("nil")) is QY_NIL

    # Should be writable at the head
    assert space.writable


def test_parse_string_literal_edge_cases():
    """Test edge cases in string literal parsing."""
    assert parse_string_literal('""') == ""
    assert parse_string_literal('"\\t\\r\\n"') == "\t\r\n"
    assert parse_string_literal('"unicode: \\u0041"') == "unicode: A"
    assert parse_string_literal("123") is _MISSING
    assert parse_string_literal('"unterminated') is _MISSING


def test_parse_number_literal_edge_cases():
    """Test edge cases in number literal parsing."""
    from qy.sem.core import FloatValue
    from qy.sem.core import IntValue

    assert parse_number_literal("0") == IntValue(0)
    assert parse_number_literal("-0") == IntValue(0)
    assert parse_number_literal("0.0") == FloatValue(0.0)
    assert parse_number_literal("1e10") == FloatValue(1e10)
    assert parse_number_literal("1.5e-3") == FloatValue(1.5e-3)
    assert parse_number_literal("inf") is _MISSING
    assert parse_number_literal("nan") is _MISSING
