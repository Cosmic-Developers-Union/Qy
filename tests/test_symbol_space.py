# coding: utf-8
"""Tests for core symbol-space implementation."""

import pytest

from qy.core.symbol_space import BindingSlot
from qy.core.symbol_space import ChainFrame
from qy.core.symbol_space import SymbolSpace
from qy.errors import QyRuntimeError
from qy.frontend.reader import Symbol

S = Symbol


def test_symbol_space_basic_lookup():
    """Test basic symbol lookup in a symbol-space."""
    space = SymbolSpace({S("x"): 10, S("y"): 20})
    assert space.lookup(S("x")) == 10
    assert space.lookup(S("y")) == 20
    assert space.lookup(S("z")) is None


def test_symbol_space_parent_lookup():
    """Test lookup through parent chain."""
    parent = SymbolSpace({S("x"): 10})
    child = parent.child({S("y"): 20})

    assert child.lookup(S("x")) == 10
    assert child.lookup(S("y")) == 20
    assert child.lookup(S("z")) is None


def test_symbol_space_shadowing():
    """Test that child can shadow parent bindings."""
    parent = SymbolSpace({S("x"): 10})
    child = parent.child({S("x"): 20})

    assert parent.lookup(S("x")) == 10
    assert child.lookup(S("x")) == 20


def test_symbol_space_define():
    """Test basic define operation."""
    space = SymbolSpace()
    result = space.define(S("x"), 42)

    assert result == 42
    assert space.lookup(S("x")) == 42


def test_symbol_space_define_allows_rebinding():
    """Test that define allows re-binding."""
    space = SymbolSpace()
    space.define(S("x"), 10)
    space.define(S("x"), 20)

    assert space.lookup(S("x")) == 20


def test_symbol_space_define_once():
    """Test define_once prevents re-binding."""
    space = SymbolSpace()
    space.define_once(S("x"), 10)

    with pytest.raises(QyRuntimeError) as exc_info:
        space.define_once(S("x"), 20)

    assert "already bound" in str(exc_info.value)
    assert space.lookup(S("x")) == 10


def test_symbol_space_define_once_allows_shadow():
    """Test that define_once in child can shadow parent."""
    parent = SymbolSpace()
    parent.define_once(S("x"), 10)

    child = parent.child()
    child.define_once(S("x"), 20)

    assert parent.lookup(S("x")) == 10
    assert child.lookup(S("x")) == 20


def test_symbol_space_hidden_bindings():
    """Test hidden bindings are not visible in normal lookup."""
    space = SymbolSpace()
    space.define(S("x"), 10)
    space.define_hidden(S("y"), 20)

    assert space.lookup(S("x")) == 10
    assert space.lookup(S("y")) == 20
    assert S("x") in space.local_bindings()
    assert S("y") not in space.local_bindings()
    assert S("y") in space.hidden_bindings()


def test_symbol_space_fold_from():
    """Test fold operation."""
    source = {S("a"): 1, S("b"): 2, S("c"): 3}
    space = SymbolSpace()

    space.fold_from(source, [S("a"), S("b")])

    assert space.lookup(S("a")) == 1
    assert space.lookup(S("b")) == 2
    assert space.lookup(S("c")) is None


def test_symbol_space_fold_from_rejects_duplicate():
    """Test fold rejects symbols already bound."""
    source = {S("a"): 1, S("b"): 2}
    space = SymbolSpace({S("a"): 10})

    with pytest.raises(QyRuntimeError) as exc_info:
        space.fold_from(source, [S("a"), S("b")])

    assert "already bound" in str(exc_info.value)


def test_symbol_space_fold_from_rejects_missing():
    """Test fold rejects missing symbols."""
    source = {S("a"): 1}
    space = SymbolSpace()

    with pytest.raises(QyRuntimeError) as exc_info:
        space.fold_from(source, [S("a"), S("b")])

    assert "no export" in str(exc_info.value)


def test_symbol_space_has_local_binding():
    """Test has_local_binding check."""
    parent = SymbolSpace({S("x"): 10})
    child = parent.child({S("y"): 20})

    assert child.has_local_binding(S("y"))
    assert not child.has_local_binding(S("x"))
    assert not child.has_local_binding(S("z"))


def test_symbol_space_all_bindings():
    """Test all_bindings includes parent chain."""
    parent = SymbolSpace({S("x"): 10, S("y"): 20})
    child = parent.child({S("y"): 30, S("z"): 40})

    all_bindings = child.all_bindings()

    assert all_bindings[S("x")] == 10
    assert all_bindings[S("y")] == 30  # child shadows parent
    assert all_bindings[S("z")] == 40


def test_symbol_space_cache():
    """Test shared cache across parent-child chain."""
    parent = SymbolSpace()
    child = parent.child()

    parent.cache_define("key1", "value1")
    assert child.cache_lookup("key1") == "value1"

    child.cache_define("key2", "value2")
    assert parent.cache_lookup("key2") == "value2"

    child.cache_discard("key1")
    with pytest.raises(KeyError):
        parent.cache_lookup("key1")


def test_symbol_space_properties():
    """Test symbol-space properties."""
    space = SymbolSpace(name="test", writable=False, lazy=True)

    assert space.name == "test"
    assert not space.writable
    assert space.lazy


def test_symbol_space_chain_frames():
    """Test chain frames generation."""
    root = SymbolSpace({S("a"): 1}, name="root")
    middle = root.child({S("b"): 2}, name="middle")
    leaf = middle.child({S("c"): 3}, name="leaf")

    chain = leaf.chain()
    frames = chain.frames()

    assert len(frames) == 3
    assert frames[0].name == "root"
    assert frames[1].name == "middle"
    assert frames[2].name == "leaf"

    assert S("a") in frames[0].bindings
    assert S("b") in frames[1].bindings
    assert S("c") in frames[2].bindings


def test_symbol_space_chain_lookup():
    """Test lookup through chain."""
    root = SymbolSpace({S("x"): 10})
    child = root.child({S("y"): 20})

    chain = child.chain()

    assert chain.lookup(S("x")) == 10
    assert chain.lookup(S("y")) == 20
    assert chain.lookup(S("z")) is None


def test_binding_slot_complete():
    """Test binding slot completion."""
    slot = BindingSlot(S("x"))

    assert not slot.completed
    assert slot.value is None

    completed = slot.complete(42)

    assert completed.completed
    assert completed.value == 42


def test_binding_slot_cannot_complete_twice():
    """Test binding slot cannot be completed twice."""
    slot = BindingSlot(S("x")).complete(10)

    with pytest.raises(QyRuntimeError) as exc_info:
        slot.complete(20)

    assert "already completed" in str(exc_info.value)


def test_chain_frame_immutability():
    """Test ChainFrame is immutable."""
    frame = ChainFrame(name="test", bindings={S("x"): 10}, writable=True, lazy=False)

    with pytest.raises((AttributeError, TypeError)):  # dataclass frozen
        frame.name = "changed"  # type: ignore


def test_symbol_space_anonymous_name():
    """Test anonymous symbol-space gets default name."""
    space = SymbolSpace()
    chain = space.chain()
    frames = chain.frames()

    assert frames[0].name == "<anonymous>"


def test_symbol_space_child_inherits_cache():
    """Test child inherits parent's cache reference."""
    parent = SymbolSpace()
    parent.cache_define("key", "value")

    child = parent.child()

    # Child should see parent's cache
    assert child.cache_lookup("key") == "value"

    # Modifications in child affect parent
    child.cache_define("key2", "value2")
    assert parent.cache_lookup("key2") == "value2"


def test_symbol_space_multiple_children_share_cache():
    """Test multiple children share the same cache."""
    parent = SymbolSpace()
    child1 = parent.child()
    child2 = parent.child()

    child1.cache_define("key", "value")

    assert child2.cache_lookup("key") == "value"
    assert parent.cache_lookup("key") == "value"


def test_symbol_space_deep_chain():
    """Test deep symbol-space chain."""
    spaces = [SymbolSpace({S(f"x{i}"): i}, name=f"level{i}") for i in range(10)]

    for i in range(1, 10):
        spaces[i] = spaces[i - 1].child(
            {S(f"x{i}"): i}, name=f"level{i}", writable=True, lazy=False
        )

    leaf = spaces[-1]

    # All symbols should be accessible
    for i in range(10):
        assert leaf.lookup(S(f"x{i}")) == i

    # Chain should have all frames
    frames = leaf.chain().frames()
    assert len(frames) == 10
    assert frames[0].name == "level0"
    assert frames[-1].name == "level9"
