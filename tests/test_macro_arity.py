# coding: utf-8
"""测试 qy.macro 模块。."""

from __future__ import annotations

import pytest

from qy.errors import QyArityError
from qy.macro import MacroDefinition
from qy.reader import Symbol


def _make_compile_time_env():
    """创建编译时环境。."""
    from qy.environment import Environment

    return Environment()


@pytest.mark.asyncio
async def test_macro_definition_expand():
    """测试宏展开。."""
    env = _make_compile_time_env()
    macro = MacroDefinition(
        name=Symbol("test-macro"),
        params=(Symbol("x"),),
        body=((Symbol("quote"), Symbol("expanded")),),
        closure=env,
    )

    result = await macro.expand((Symbol("arg"),))
    assert result == Symbol("expanded")


@pytest.mark.asyncio
async def test_macro_definition_arity_error():
    """测试宏参数数量错误。."""
    env = _make_compile_time_env()
    macro = MacroDefinition(
        name=Symbol("test-macro"),
        params=(Symbol("x"), Symbol("y")),
        body=((Symbol("quote"), Symbol("expanded")),),
        closure=env,
    )

    with pytest.raises(QyArityError) as exc_info:
        await macro.expand((Symbol("arg"),))

    assert "expects 2 arguments, got 1" in str(exc_info.value)
    assert exc_info.value.metadata["expected"] == 2
    assert exc_info.value.metadata["actual"] == 1
