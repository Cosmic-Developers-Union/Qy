# coding: utf-8
"""Tests for core symbol-space implementation."""

import pytest

from qy.core.symbol_space import MISSING
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
    assert space.lookup(S("z")) is MISSING


def test_symbol_space_parent_lookup():
    """Test resolve through parent chain (lookup is single-layer)."""
    parent = SymbolSpace({S("x"): 10})
    child = parent.child({S("y"): 20})

    assert child.resolve(S("x")) == 10
    assert child.resolve(S("y")) == 20
    assert child.resolve(S("z")) is MISSING
    # lookup is single-layer
    assert child.lookup(S("x")) is MISSING
    assert child.lookup(S("y")) == 20


def test_symbol_space_shadowing():
    """Test that child can shadow parent bindings."""
    parent = SymbolSpace({S("x"): 10})
    child = parent.child({S("x"): 20})

    assert parent.resolve(S("x")) == 10
    assert child.resolve(S("x")) == 20


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

    assert parent.resolve(S("x")) == 10
    assert child.resolve(S("x")) == 20


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
    assert space.lookup(S("c")) is MISSING


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
    """Test resolve through chain."""
    root = SymbolSpace({S("x"): 10})
    child = root.child({S("y"): 20})

    chain = child.chain()

    assert chain.resolve(S("x")) == 10
    assert chain.resolve(S("y")) == 20
    assert chain.resolve(S("z")) is MISSING


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

    # All symbols should be accessible (chain lookup)
    for i in range(10):
        assert leaf.resolve(S(f"x{i}")) == i

    # Chain should have all frames
    frames = leaf.chain().frames()
    assert len(frames) == 10
    assert frames[0].name == "level0"
    assert frames[-1].name == "level9"


# ---------------------------------------------------------------------------
# Phase 1 additions: contains primitive + MISSING semantics + dynamic spaces
# ---------------------------------------------------------------------------


def test_contains_finite_space():
    """Contains 检测有限空间的本层成员。."""
    space = SymbolSpace({S("x"): 10, S("y"): None})
    assert space.contains(S("x"))
    assert space.contains(S("y"))  # 绑定到 None 仍然算"在空间内"
    assert not space.contains(S("z"))


def test_contains_does_not_walk_parent():
    """Contains 仅看本层,不走父链。."""
    parent = SymbolSpace({S("x"): 10})
    child = parent.child({S("y"): 20})
    assert child.contains(S("y"))
    assert not child.contains(S("x"))  # parent 的不算


def test_contains_infinite_space():
    """Contains 对无限空间通过 membership 判断。."""

    def is_pos_int(s):
        return s.name.isdigit()

    def resolve(s):
        return int(s.name) if s.name.isdigit() else MISSING

    space = SymbolSpace({}, membership=is_pos_int, resolver=resolve)
    assert space.contains(S("42"))
    assert space.contains(S("0"))
    assert not space.contains(S("foo"))


def test_lookup_returns_missing_for_absent():
    """Lookup 在缺失时返回 MISSING,不再返回 None。."""
    space = SymbolSpace({S("x"): 10})
    assert space.lookup(S("missing")) is MISSING


def test_missing_is_distinct_from_none():
    """绑定到 None 的 symbol lookup 返回 None;不存在的返回 MISSING。."""
    space = SymbolSpace({S("explicit_none"): None})
    assert space.lookup(S("explicit_none")) is None
    assert space.lookup(S("absent")) is MISSING
    assert space.contains(S("explicit_none"))
    assert not space.contains(S("absent"))


def test_membership_resolver_must_be_paired():
    """Membership 与 resolver 必须同时提供或同时不提供。."""
    import pytest

    with pytest.raises(ValueError):
        SymbolSpace({}, membership=lambda s: True)

    with pytest.raises(ValueError):
        SymbolSpace({}, resolver=lambda s: MISSING)


def test_finite_and_infinite_coexist():
    """同一个 ss 可同时持有 fixed bindings 和 (membership, resolver)。.

    这是 number-ss 的目标形态: 既有 ``+`` / ``-`` 算子, 又能识别 ``42``。
    """
    plus_op = object()
    space = SymbolSpace(
        {S("+"): plus_op},
        membership=lambda s: s.name.isdigit(),
        resolver=lambda s: int(s.name) if s.name.isdigit() else MISSING,
    )
    # fixed binding
    assert space.contains(S("+"))
    assert space.lookup(S("+")) is plus_op
    # dynamic binding
    assert space.contains(S("42"))
    assert space.lookup(S("42")) == 42
    # neither
    assert not space.contains(S("foo"))
    assert space.lookup(S("foo")) is MISSING


def test_resolve_walks_chain_for_dynamic_space():
    """Resolve 沿父链查找 (含动态空间)。."""
    parent = SymbolSpace({S("x"): 10})

    def _dyn_resolver(s):
        if s.name.startswith("dyn-"):
            return f"dynamic-{s.name}"
        return MISSING

    child = parent.child(
        {},
        membership=lambda s: s.name.startswith("dyn-"),
        resolver=_dyn_resolver,
    )
    assert child.resolve(S("x")) == 10  # parent 命中
    assert child.resolve(S("dyn-foo")) == "dynamic-dyn-foo"  # child 动态命中
    assert child.resolve(S("missing")) is MISSING


def test_shadow_in_let_overrides_dynamic_space():
    """子空间的 fixed binding 可以 shadow 父空间的动态命中。.

    关键场景: ``(let ((+ ...)) ...)`` 在 head 层覆盖 number-ss 的 ``+``。
    """
    plus_op = object()
    user_plus = object()
    number_ss = SymbolSpace({S("+"): plus_op}, name="number-ss", writable=False)
    head = number_ss.child({S("+"): user_plus}, name="head")
    assert head.resolve(S("+")) is user_plus
    assert number_ss.resolve(S("+")) is plus_op
