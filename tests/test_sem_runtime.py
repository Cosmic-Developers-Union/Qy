# coding: utf-8
"""测试 qy.sem.runtime 模块。."""

from __future__ import annotations

import pytest

from qy.core.syntax import Symbol
from qy.sem.runtime import EffectDefinition


def test_effect_definition_creation():
    """测试创建 EffectDefinition。."""
    effect = EffectDefinition(
        name=Symbol("test-effect"),
        resumable=True,
        doc="Test effect",
    )
    assert effect.name.name == "test-effect"
    assert effect.resumable is True
    assert effect.doc == "Test effect"


def test_effect_definition_defaults():
    """测试 EffectDefinition 默认值。."""
    effect = EffectDefinition(name=Symbol("test-effect"))
    assert effect.resumable is True
    assert effect.doc == ""


def test_effect_definition_immutable():
    """测试 EffectDefinition 是不可变的。."""
    effect = EffectDefinition(name=Symbol("test-effect"))

    with pytest.raises(AttributeError):
        effect.resumable = False  # ty: ignore[invalid-assignment]
