# coding: utf-8
"""Tests for session profile configuration."""

from qy.frontend.reader import Symbol
from qy.sem.core import FloatValue
from qy.sem.core import IntValue
from qy.session.profile import ProfileConfig

S = Symbol


def test_profile_config_default_literal_resolver():
    """Test default literal resolver."""
    profile = ProfileConfig()

    # Should resolve number literals
    assert profile.resolve_literal(S("42")) == IntValue(42)
    assert profile.resolve_literal(S("3.14")) == FloatValue(3.14)

    # Should resolve string literals
    assert profile.resolve_literal(S('"hello"')) == "hello"


def test_profile_config_custom_literal_resolver():
    """Test custom literal resolver."""

    def custom_resolver(symbol: Symbol) -> object:
        if symbol.name == "answer":
            return 42
        if symbol.name == "pi":
            return 3.14159
        from qy.session.pre_ss import resolve_default_literal

        return resolve_default_literal(symbol)

    profile = ProfileConfig(custom_resolver)

    assert profile.resolve_literal(S("answer")) == 42
    assert profile.resolve_literal(S("pi")) == 3.14159
    assert profile.resolve_literal(S("123")) == 123


def test_profile_config_create_standard_space():
    """Test creating standard symbol-space."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    # Should have stdlib bindings
    assert space.lookup(S("+")) is not None
    assert space.lookup(S("-")) is not None
    assert space.lookup(S("*")) is not None

    # Should have writable head (name changed with pre-ss)
    assert space.name in ("writable-head", "pre-ssc-head")
    assert space.writable

    # Parent should be stdlib layer (or intermediate layer with pre-ss)
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
    """Test that standard space allows shadowing stdlib."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    # Should be able to shadow stdlib operators
    space.define(S("+"), "my custom plus")
    assert space.lookup(S("+")) == "my custom plus"


def test_profile_config_standard_space_stdlib_not_writable():
    """Test that stdlib layer is not writable."""
    profile = ProfileConfig()
    space = profile.create_standard_space()

    # Get stdlib layer
    stdlib = space.parent
    assert stdlib is not None
    assert not stdlib.writable


def test_profile_config_with_custom_resolver_in_standard_space():
    """Test custom resolver works with standard space."""

    def custom_resolver(symbol: Symbol) -> object:
        if symbol.name == "magic":
            return 999
        from qy.session.pre_ss import resolve_default_literal

        return resolve_default_literal(symbol)

    profile = ProfileConfig(custom_resolver)
    space = profile.create_standard_space()

    # Custom resolver should work
    assert profile.resolve_literal(S("magic")) == 999

    # Standard bindings should still work
    assert space.lookup(S("+")) is not None


def test_profile_config_literal_resolver_property():
    """Test literal_resolver property."""

    def custom_resolver(symbol: Symbol) -> object:
        return 42

    profile = ProfileConfig(custom_resolver)

    assert profile.literal_resolver is custom_resolver


def test_profile_config_none_literal_resolver():
    """Test None literal resolver uses default."""
    profile = ProfileConfig(None)

    # Should use default resolver
    assert profile.resolve_literal(S("42")) == IntValue(42)
    assert profile.resolve_literal(S('"test"')) == "test"
