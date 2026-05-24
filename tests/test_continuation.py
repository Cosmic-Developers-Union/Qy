# coding: utf-8
"""测试 qy.continuation 模块。."""

from __future__ import annotations

import pytest

from qy.continuation import QyContinuation
from qy.continuation import _await_if_needed


@pytest.mark.asyncio
async def test_await_if_needed_with_coroutine():
    """测试 _await_if_needed 处理协程。."""

    async def async_func():
        return 42

    result = await _await_if_needed(async_func())
    assert result == 42


@pytest.mark.asyncio
async def test_await_if_needed_with_non_coroutine():
    """测试 _await_if_needed 处理非协程值。."""
    result = await _await_if_needed(42)
    assert result == 42


def test_qy_continuation_creation():
    """测试创建 QyContinuation。."""

    def resume_func(value):
        return value * 2

    cont = QyContinuation(effect="test-effect", resumable=True, _resume=resume_func)
    assert cont.effect == "test-effect"
    assert cont.resumable is True


def test_qy_continuation_non_resumable():
    """测试创建不可恢复的 continuation。."""

    def resume_func(value):
        return value

    cont = QyContinuation(effect="test-effect", resumable=False, _resume=resume_func)
    assert cont.effect == "test-effect"
    assert cont.resumable is False


@pytest.mark.asyncio
async def test_qy_continuation_resume():
    """测试恢复 continuation。."""

    def resume_func(value):
        return value * 2

    cont = QyContinuation(effect="test-effect", resumable=True, _resume=resume_func)
    result = await cont.resume(21)
    assert result == 42


@pytest.mark.asyncio
async def test_qy_continuation_resume_non_resumable():
    """测试恢复不可恢复的 continuation 抛出异常。."""
    from qy.errors import QyEffectError

    def resume_func(value):
        return value

    cont = QyContinuation(effect="test-effect", resumable=False, _resume=resume_func)

    with pytest.raises(QyEffectError) as exc_info:
        await cont.resume(42)

    assert "not resumable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_qy_continuation_resume_twice():
    """测试 multi-shot continuation 允许多次恢复。."""

    def resume_func(value):
        return value

    cont = QyContinuation(effect="test-effect", resumable=True, _resume=resume_func)
    result1 = await cont.resume(42)
    result2 = await cont.resume(99)

    assert result1 == 42
    assert result2 == 99
