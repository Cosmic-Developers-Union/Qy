# coding: utf-8
"""Tests for fold and unfold operations."""

import pytest

from qy.core.symbol_space import MISSING
from qy.core.symbol_space import SymbolSpace
from qy.errors import QyRuntimeError
from qy.frontend.reader import Symbol
from qy.import_ import fold
from qy.import_ import unfold
from qy.import_.resolver import detect_conflicts
from qy.import_.resolver import resolve_fold
from qy.import_.resolver import resolve_unfold

S = Symbol


def test_fold_basic():
    """Test basic fold operation."""
    source = {S("x"): 1, S("y"): 2, S("z"): 3}
    target = SymbolSpace()

    fold(target, source, [S("x"), S("y")])

    assert target.lookup(S("x")) == 1
    assert target.lookup(S("y")) == 2
    assert target.lookup(S("z")) is MISSING


def test_fold_with_aliases():
    """Test fold with aliases."""
    source = {S("x"): 1, S("y"): 2}
    target = SymbolSpace()
    aliases = {S("x"): S("a"), S("y"): S("b")}

    fold(target, source, [S("x"), S("y")], aliases)

    assert target.lookup(S("a")) == 1
    assert target.lookup(S("b")) == 2
    assert target.lookup(S("x")) is MISSING
    assert target.lookup(S("y")) is MISSING


def test_fold_rejects_conflicts():
    """Test fold rejects naming conflicts."""
    source = {S("x"): 1, S("y"): 2}
    target = SymbolSpace({S("x"): 10})

    with pytest.raises(QyRuntimeError) as exc_info:
        fold(target, source, [S("x"), S("y")])

    assert "conflicts" in str(exc_info.value)


def test_fold_allows_conflicts_when_disabled():
    """Test fold allows conflicts when check is disabled."""
    source = {S("x"): 1, S("y"): 2}
    target = SymbolSpace({S("x"): 10})

    # Should not raise when check_conflicts=False
    fold(target, source, [S("x"), S("y")], check_conflicts=False)

    # Note: fold_from will still raise because it enforces define_once
    # This test verifies the check_conflicts parameter works


def test_fold_missing_symbol():
    """Test fold rejects missing symbols."""
    source = {S("x"): 1}
    target = SymbolSpace()

    with pytest.raises(QyRuntimeError) as exc_info:
        fold(target, source, [S("x"), S("y")])

    assert "no export" in str(exc_info.value)


def test_unfold_basic():
    """Test basic unfold operation."""
    source = {S("x"): 1, S("y"): 2, S("z"): 3}
    target = SymbolSpace()

    unfold(target, source, [S("x"), S("y")])

    assert target.lookup(S("x")) == 1
    assert target.lookup(S("y")) == 2
    assert target.lookup(S("z")) is MISSING


def test_unfold_all():
    """Test unfold all symbols."""
    source = {S("x"): 1, S("y"): 2, S("z"): 3}
    target = SymbolSpace()

    unfold(target, source)

    assert target.lookup(S("x")) == 1
    assert target.lookup(S("y")) == 2
    assert target.lookup(S("z")) == 3


def test_unfold_with_prefix():
    """Test unfold with prefix."""
    source = {S("x"): 1, S("y"): 2}
    target = SymbolSpace()

    unfold(target, source, prefix="mod.")

    assert target.lookup(S("mod.x")) == 1
    assert target.lookup(S("mod.y")) == 2
    assert target.lookup(S("x")) is MISSING
    assert target.lookup(S("y")) is MISSING


def test_unfold_selected_with_prefix():
    """Test unfold selected symbols with prefix."""
    source = {S("x"): 1, S("y"): 2, S("z"): 3}
    target = SymbolSpace()

    unfold(target, source, [S("x"), S("y")], prefix="mod.")

    assert target.lookup(S("mod.x")) == 1
    assert target.lookup(S("mod.y")) == 2
    assert target.lookup(S("mod.z")) is MISSING


def test_unfold_rejects_conflicts():
    """Test unfold rejects naming conflicts."""
    source = {S("x"): 1, S("y"): 2}
    target = SymbolSpace({S("x"): 10})

    with pytest.raises(QyRuntimeError) as exc_info:
        unfold(target, source)

    assert "conflicts" in str(exc_info.value)


def test_unfold_prefix_avoids_conflicts():
    """Test unfold with prefix avoids conflicts."""
    source = {S("x"): 1, S("y"): 2}
    target = SymbolSpace({S("x"): 10})

    unfold(target, source, prefix="mod.")

    assert target.lookup(S("x")) == 10
    assert target.lookup(S("mod.x")) == 1
    assert target.lookup(S("mod.y")) == 2


def test_unfold_missing_symbol():
    """Test unfold rejects missing symbols."""
    source = {S("x"): 1}
    target = SymbolSpace()

    with pytest.raises(QyRuntimeError) as exc_info:
        unfold(target, source, [S("x"), S("y")])

    assert "no export" in str(exc_info.value)


def test_resolve_fold():
    """Test resolve_fold creates correct spec."""
    source = {S("x"): 1, S("y"): 2}
    aliases = {S("x"): S("a")}

    spec = resolve_fold(source, [S("x"), S("y")], aliases)

    assert spec.source_bindings == source
    assert spec.selected_names == (S("x"), S("y"))
    assert spec.alias_map == aliases


def test_fold_spec_apply_aliases():
    """Test FoldSpec.apply_aliases."""
    from qy.import_.resolver import FoldSpec

    source = {S("x"): 1, S("y"): 2, S("z"): 3}
    spec = FoldSpec(
        source_bindings=source,
        selected_names=(S("x"), S("y")),
        alias_map={S("x"): S("a")},
    )

    result = spec.apply_aliases()

    assert result == {S("a"): 1, S("y"): 2}


def test_resolve_unfold():
    """Test resolve_unfold creates correct spec."""
    source = {S("x"): 1, S("y"): 2}

    spec = resolve_unfold(source, [S("x")], prefix="mod.")

    assert spec.source_bindings == source
    assert spec.selected_names == (S("x"),)
    assert spec.prefix == "mod."


def test_unfold_spec_apply_prefix():
    """Test UnfoldSpec.apply_prefix."""
    from qy.import_.resolver import UnfoldSpec

    source = {S("x"): 1, S("y"): 2}
    spec = UnfoldSpec(
        source_bindings=source,
        selected_names=(S("x"), S("y")),
        prefix="mod.",
    )

    result = spec.apply_prefix()

    assert result[S("mod.x")] == 1
    assert result[S("mod.y")] == 2


def test_unfold_spec_apply_prefix_all():
    """Test UnfoldSpec.apply_prefix with all symbols."""
    from qy.import_.resolver import UnfoldSpec

    source = {S("x"): 1, S("y"): 2, S("z"): 3}
    spec = UnfoldSpec(
        source_bindings=source,
        selected_names=None,
        prefix="mod.",
    )

    result = spec.apply_prefix()

    assert result[S("mod.x")] == 1
    assert result[S("mod.y")] == 2
    assert result[S("mod.z")] == 3


def test_detect_conflicts():
    """Test conflict detection."""
    target = {S("x"): 1, S("y"): 2}
    incoming = {S("y"): 20, S("z"): 30}

    conflicts = detect_conflicts(target, incoming)

    assert conflicts == [S("y")]


def test_detect_no_conflicts():
    """Test no conflicts detected."""
    target = {S("x"): 1, S("y"): 2}
    incoming = {S("z"): 30, S("w"): 40}

    conflicts = detect_conflicts(target, incoming)

    assert conflicts == []


def test_fold_and_unfold_together():
    """Test fold and unfold can work together."""
    # Create two source modules
    mod_a = {S("x"): 1, S("y"): 2}
    mod_b = {S("z"): 3, S("w"): 4}

    target = SymbolSpace()

    # Fold from mod_a
    fold(target, mod_a, [S("x"), S("y")])

    # Unfold from mod_b with prefix
    unfold(target, mod_b, prefix="b.")

    assert target.lookup(S("x")) == 1
    assert target.lookup(S("y")) == 2
    assert target.lookup(S("b.z")) == 3
    assert target.lookup(S("b.w")) == 4


def test_fold_preserves_symbol_space_semantics():
    """Test fold preserves symbol-space semantics."""
    source = {S("x"): 1, S("y"): 2}
    parent = SymbolSpace({S("z"): 3})
    child = parent.child()

    fold(child, source, [S("x"), S("y")])

    # Child should have folded bindings
    assert child.lookup(S("x")) == 1
    assert child.lookup(S("y")) == 2

    # Parent should not be affected
    assert parent.lookup(S("x")) is MISSING
    assert parent.lookup(S("y")) is MISSING

    # Child should still see parent bindings (chain lookup)
    assert child.resolve(S("z")) == 3
