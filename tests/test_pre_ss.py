# coding: utf-8
"""Tests for pre-symbol-space implementation."""

import pytest

from qy.core.symbol_space import SymbolSpace
from qy.core.syntax import nil as QY_NIL
from qy.errors import QyResolveError
from qy.frontend.reader import Symbol
from qy.sem.core import T as QY_T
from qy.session.pre_ss import _MISSING
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
from qy.session.pre_ss import resolve_literal_in_pre_ss

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
    lisp = create_lisp_ss()

    assert lisp.name == "lisp-ss"
    assert not lisp.writable
    assert lisp.lookup(S("T")) is QY_T
    assert lisp.lookup(S("nil")) is QY_NIL
    assert lisp.lookup(S("true")) is QY_T
    assert lisp.lookup(S("false")) is QY_NIL
    assert lisp.lookup(S("none")) is None
    assert lisp.lookup(S("undefined")) is None


def test_create_number_ss():
    """Test number-ss creation."""
    number = create_number_ss()

    assert number.name == "number-ss"
    assert not number.writable
    assert number.parent is None


def test_create_string_ss():
    """Test string-ss creation."""
    string = create_string_ss()

    assert string.name == "string-ss"
    assert not string.writable
    assert string.parent is None


def test_create_value_ss():
    """Test value-ss creation."""
    value = create_value_ss()

    assert value.name == "value-ss"
    assert not value.writable


def test_create_literal_ss():
    """Test literal-ss creation with all literal types."""
    literal = create_literal_ss()

    assert literal.name == "value-ss"
    assert not literal.writable
    # Should have lisp-ss in parent chain
    assert literal.lookup(S("T")) is QY_T
    assert literal.lookup(S("nil")) is QY_NIL


def test_create_pre_ssc_without_stdlib():
    """Test pre-ssc creation without stdlib."""
    pre_ssc = create_pre_ssc()

    assert pre_ssc.name == "pre-ssc-head"
    assert pre_ssc.writable
    # Should have lisp-ss in parent chain
    assert pre_ssc.lookup(S("T")) is QY_T
    assert pre_ssc.lookup(S("nil")) is QY_NIL


def test_create_pre_ssc_with_stdlib():
    """Test pre-ssc creation with stdlib."""
    stdlib = SymbolSpace({S("foo"): "bar"}, name="test-stdlib")
    pre_ssc = create_pre_ssc(stdlib)

    assert pre_ssc.name == "pre-ssc-head"
    assert pre_ssc.writable
    # Should have both lisp-ss and stdlib in parent chain
    assert pre_ssc.lookup(S("T")) is QY_T
    assert pre_ssc.lookup(S("foo")) == "bar"


def test_resolve_literal_in_pre_ss_lisp_values():
    """Test resolving Lisp values through pre-ss."""
    pre_ss = create_pre_ssc()

    result_t = resolve_literal_in_pre_ss(S("T"), pre_ss)
    result_nil = resolve_literal_in_pre_ss(S("nil"), pre_ss)
    result_true = resolve_literal_in_pre_ss(S("true"), pre_ss)
    result_false = resolve_literal_in_pre_ss(S("false"), pre_ss)
    result_none = resolve_literal_in_pre_ss(S("none"), pre_ss)

    assert result_t is QY_T
    assert result_nil is QY_NIL
    assert result_true is QY_T
    assert result_false is QY_NIL
    assert result_none is None


def test_resolve_literal_in_pre_ss_numbers():
    """Test resolving number literals through pre-ss returns semantic values."""
    from qy.sem.core import FloatValue
    from qy.sem.core import IntValue

    pre_ss = create_pre_ssc()

    result_int = resolve_literal_in_pre_ss(S("123"), pre_ss)
    assert isinstance(result_int, IntValue)
    assert result_int.value == 123

    result_neg = resolve_literal_in_pre_ss(S("-456"), pre_ss)
    assert isinstance(result_neg, IntValue)
    assert result_neg.value == -456

    result_float = resolve_literal_in_pre_ss(S("3.14"), pre_ss)
    assert isinstance(result_float, FloatValue)
    assert result_float.value == 3.14

    result_neg_float = resolve_literal_in_pre_ss(S("-2.5"), pre_ss)
    assert isinstance(result_neg_float, FloatValue)
    assert result_neg_float.value == -2.5


def test_resolve_literal_in_pre_ss_strings():
    """Test resolving string literals through pre-ss."""
    pre_ss = create_pre_ssc()

    assert resolve_literal_in_pre_ss(S('"hello"'), pre_ss) == "hello"
    assert resolve_literal_in_pre_ss(S('"world\\n"'), pre_ss) == "world\n"
    assert resolve_literal_in_pre_ss(S('r"raw\\n"'), pre_ss) == "raw\\n"


def test_resolve_literal_in_pre_ss_undefined():
    """Test resolving undefined symbols returns _MISSING."""
    pre_ss = create_pre_ssc()

    assert resolve_literal_in_pre_ss(S("undefined"), pre_ss) is _MISSING
    assert resolve_literal_in_pre_ss(S("not-a-literal"), pre_ss) is _MISSING


def test_resolve_literal_in_pre_ss_with_user_bindings():
    """Test that user bindings in pre-ss take precedence."""
    pre_ss = create_pre_ssc()
    pre_ss.define(S("custom"), "custom-value")

    assert resolve_literal_in_pre_ss(S("custom"), pre_ss) == "custom-value"


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

    # Should have: lisp-ss -> value-ss -> stdlib -> pre-ssc-head
    assert "lisp-ss" in frame_names
    assert "value-ss" in frame_names
    assert "stdlib" in frame_names
    assert "pre-ssc-head" in frame_names


def test_literal_ss_with_parent():
    """Test literal-ss creation with custom parent."""
    parent = SymbolSpace({S("parent-sym"): "parent-val"}, name="parent")
    literal = create_literal_ss(parent=parent)

    # Should be able to look up parent symbols
    assert literal.lookup(S("parent-sym")) == "parent-val"
    # And lisp symbols
    assert literal.lookup(S("T")) is QY_T


def test_number_ss_with_parent():
    """Test number-ss creation with parent."""
    parent = SymbolSpace({S("x"): 10}, name="parent")
    number = create_number_ss(parent=parent)

    assert number.parent is parent
    assert number.lookup(S("x")) == 10


def test_string_ss_with_parent():
    """Test string-ss creation with parent."""
    parent = SymbolSpace({S("x"): 10}, name="parent")
    string = create_string_ss(parent=parent)

    assert string.parent is parent
    assert string.lookup(S("x")) == 10


def test_value_ss_with_parent():
    """Test value-ss creation with parent."""
    parent = SymbolSpace({S("x"): 10}, name="parent")
    value = create_value_ss(parent=parent)

    assert value.parent is parent
    assert value.lookup(S("x")) == 10


def test_resolve_literal_priority():
    """Test that symbol-space bindings take priority over literal parsing."""
    pre_ss = create_pre_ssc()
    # Define a symbol that looks like a number
    pre_ss.define(S("123"), "not-a-number")

    # Should return the binding, not parse as number
    assert resolve_literal_in_pre_ss(S("123"), pre_ss) == "not-a-number"


def test_profile_config_with_pre_ss():
    """Test ProfileConfig using pre-ss for literal resolution."""
    from qy.sem.core import IntValue
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig(use_pre_ss=True)

    # Should resolve literals correctly
    assert profile.resolve_literal(S("T")) is QY_T
    assert profile.resolve_literal(S("nil")) is QY_NIL
    assert profile.resolve_literal(S("123")) == IntValue(123)
    assert profile.resolve_literal(S('"hello"')) == "hello"

    # Should raise for undefined symbols
    with pytest.raises(QyResolveError) as exc_info:
        profile.resolve_literal(S("undefined"))
    assert "unresolved symbol" in str(exc_info.value)


def test_profile_config_legacy_mode():
    """Test ProfileConfig in legacy mode (use_pre_ss=False)."""
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig(use_pre_ss=False)

    # Should still resolve literals using old resolver
    assert profile.resolve_literal(S("T")) is QY_T
    assert profile.resolve_literal(S("nil")) is QY_NIL
    assert profile.resolve_literal(S("123")) == 123
    assert profile.resolve_literal(S('"hello"')) == "hello"


def test_profile_config_create_standard_space_with_pre_ss():
    """Test creating standard space with pre-ss integration."""
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig(use_pre_ss=True)
    space = profile.create_standard_space()

    # Should have lisp values
    assert space.lookup(S("T")) is QY_T
    assert space.lookup(S("nil")) is QY_NIL

    # Should be writable at the head
    assert space.writable


def test_profile_config_create_standard_space_legacy():
    """Test creating standard space in legacy mode."""
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig(use_pre_ss=False)
    space = profile.create_standard_space()

    # Should be writable
    assert space.writable
    assert space.name == "writable-head"


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
