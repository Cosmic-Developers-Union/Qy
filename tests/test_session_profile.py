# coding: utf-8
"""Tests for session profile configuration."""

import pytest

from qy.errors import QyResolveError
from qy.frontend.reader import Symbol
from qy.sem.core import FloatValue
from qy.sem.core import IntValue
from qy.session.profile import ProfileConfig

S = Symbol


def test_profile_config_default_resolves_literals_via_standard_space():
    """Default ProfileConfig + standard space resolves number/string literals via ssc walk."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    assert space.resolve(S("42")) == IntValue(42)
    assert space.resolve(S("3.14")) == FloatValue(3.14)
    assert space.resolve(S('"hello"')) == "hello"


def test_profile_config_default_resolve_literal_for_literals_and_unknown():
    """ProfileConfig.resolve_literal: 字面量经 fallback pre-ssc 解析; 未知符号抛 unresolved。.

    字面量解析的主路径在 ssc walk; profile 内建 fallback pre-ssc 处理直接构造
    ``RuntimeSpace(bindings_dict, ...)`` 这类绕过 ``create_standard_space`` 的入口
    需要的字面量。
    """
    profile = ProfileConfig()
    # literal: fallback pre-ssc 解析。
    assert profile.resolve_literal(S("42")) == IntValue(42)
    # 非字面量: 无用户钩子时抛。
    with pytest.raises(QyResolveError):
        profile.resolve_literal(S("definitely-not-a-literal"))


def test_profile_config_custom_literal_resolver():
    """Custom literal resolver hook is honored by profile.resolve_literal."""

    def custom_resolver(symbol: Symbol) -> object:
        if symbol.name == "answer":
            return 42
        if symbol.name == "pi":
            return 3.14159
        raise QyResolveError(f"unresolved symbol {symbol.name!r}")

    profile = ProfileConfig(custom_resolver)

    assert profile.resolve_literal(S("answer")) == 42
    assert profile.resolve_literal(S("pi")) == 3.14159


def test_profile_config_create_standard_space():
    """Test creating standard symbol-space."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    # ``+`` etc. live in number-ss, so resolve (chain walk) finds them.
    assert space.resolve(S("+")) is not None
    assert space.resolve(S("-")) is not None
    assert space.resolve(S("*")) is not None

    # head layer is writable and named
    assert space.name == "pre-ssc-head"
    assert space.writable

    # Parent should be stdlib layer (immutable)
    assert space.parent is not None
    assert not space.parent.writable


def test_profile_config_standard_space_allows_user_definitions():
    """Test that standard space allows user definitions."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    # Should be able to define new symbols
    space.define(S("my-var"), 100)
    assert space.lookup(S("my-var")) == 100


def test_profile_config_standard_space_allows_shadowing():
    """Test that standard space allows shadowing stdlib / number-ss."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    # Should be able to shadow operators (resolve walks chain, head wins)
    space.define(S("+"), "my custom plus")
    assert space.resolve(S("+")) == "my custom plus"


def test_profile_config_standard_space_stdlib_not_writable():
    """Test that stdlib layer is not writable."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    # Get stdlib layer
    stdlib = space.parent
    assert stdlib is not None
    assert not stdlib.writable


def test_profile_config_with_custom_resolver_in_standard_space():
    """Test custom resolver works alongside standard space."""

    def custom_resolver(symbol: Symbol) -> object:
        if symbol.name == "magic":
            return 999
        raise QyResolveError(f"unresolved symbol {symbol.name!r}")

    profile = ProfileConfig(custom_resolver)
    space = profile.create_standard_space()

    # Custom resolver runs only via profile.resolve_literal (after ssc miss).
    assert profile.resolve_literal(S("magic")) == 999

    # Standard bindings should still work via chain walk.
    assert space.resolve(S("+")) is not None


def test_profile_config_literal_resolver_property():
    """Test literal_resolver property."""

    def custom_resolver(symbol: Symbol) -> object:
        return 42

    profile = ProfileConfig(custom_resolver)

    assert profile.literal_resolver is custom_resolver


def test_profile_config_none_literal_resolver_walks_ssc():
    """Without a user hook, ProfileConfig still serves literals via ssc walk."""
    profile = ProfileConfig(None)
    space = profile.create_standard_space()

    assert space.resolve(S("42")) == IntValue(42)
    assert space.resolve(S('"test"')) == "test"
