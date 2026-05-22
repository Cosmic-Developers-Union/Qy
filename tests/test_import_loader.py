# coding: utf-8
"""Tests for module loader."""

import pytest

from qy.core.symbol_space import SymbolSpace
from qy.errors import QyRuntimeError
from qy.frontend.reader import Symbol
from qy.import_.loader import ModuleLoader
from qy.import_.loader import get_global_loader
from qy.import_.loader import load_named_space
from qy.import_.loader import set_global_loader

S = Symbol


def test_module_loader_basic():
    """Test basic module loading."""
    loader = ModuleLoader()

    # Create a test module
    test_space = SymbolSpace({S("x"): 1, S("y"): 2}, name="test")

    # Cache it
    loader.cache("test", test_space)

    # Load it
    loaded = loader.load("test")

    assert loaded is test_space
    assert loaded.lookup(S("x")) == 1


def test_module_loader_caches_modules():
    """Test that loader caches modules."""
    loader = ModuleLoader()

    test_space = SymbolSpace({S("x"): 1}, name="test")
    loader.cache("test", test_space)

    # Load twice
    first = loader.load("test")
    second = loader.load("test")

    # Should be the same instance
    assert first is second


def test_module_loader_detects_circular_dependency():
    """Test circular dependency detection."""

    class CircularLoader(ModuleLoader):
        def _load_module(self, name: str) -> SymbolSpace:
            # Try to load itself
            return self.load(name)

    loader = CircularLoader()

    with pytest.raises(QyRuntimeError) as exc_info:
        loader.load("circular")

    assert "circular dependency" in str(exc_info.value)


def test_module_loader_has_cached():
    """Test has_cached check."""
    loader = ModuleLoader()

    assert not loader.has_cached("test")

    test_space = SymbolSpace({S("x"): 1}, name="test")
    loader.cache("test", test_space)

    assert loader.has_cached("test")


def test_module_loader_clear_cache():
    """Test cache clearing."""
    loader = ModuleLoader()

    test_space = SymbolSpace({S("x"): 1}, name="test")
    loader.cache("test", test_space)

    assert loader.has_cached("test")

    loader.clear_cache()

    assert not loader.has_cached("test")


def test_module_loader_unconfigured():
    """Test that unconfigured loader raises error."""
    loader = ModuleLoader()

    with pytest.raises(QyRuntimeError) as exc_info:
        loader.load("nonexistent")

    assert "not configured" in str(exc_info.value)


def test_global_loader():
    """Test global loader functions."""
    # Get global loader
    loader1 = get_global_loader()
    loader2 = get_global_loader()

    # Should be the same instance
    assert loader1 is loader2

    # Set a new loader
    new_loader = ModuleLoader()
    set_global_loader(new_loader)

    loader3 = get_global_loader()
    assert loader3 is new_loader
    assert loader3 is not loader1


def test_load_named_space():
    """Test load_named_space convenience function."""

    # Create a custom loader
    class TestLoader(ModuleLoader):
        def _load_module(self, name: str) -> SymbolSpace:
            return SymbolSpace({S("loaded"): True}, name=name)

    loader = TestLoader()
    set_global_loader(loader)

    # Load using convenience function
    space = load_named_space("test")

    assert space.lookup(S("loaded")) is True
    assert space.name == "test"


def test_module_loader_multiple_modules():
    """Test loading multiple modules."""
    loader = ModuleLoader()

    mod_a = SymbolSpace({S("x"): 1}, name="mod_a")
    mod_b = SymbolSpace({S("y"): 2}, name="mod_b")

    loader.cache("mod_a", mod_a)
    loader.cache("mod_b", mod_b)

    loaded_a = loader.load("mod_a")
    loaded_b = loader.load("mod_b")

    assert loaded_a.lookup(S("x")) == 1
    assert loaded_b.lookup(S("y")) == 2
    assert loaded_a is not loaded_b


def test_module_loader_loading_state_cleanup():
    """Test that loading state is cleaned up on error."""

    class FailingLoader(ModuleLoader):
        def _load_module(self, name: str) -> SymbolSpace:
            raise RuntimeError("Load failed")

    loader = FailingLoader()

    # First load should fail
    with pytest.raises(RuntimeError):
        loader.load("test")

    # Loading state should be cleaned up
    assert "test" not in loader._loading

    # Should be able to try again
    with pytest.raises(RuntimeError):
        loader.load("test")
