# coding: utf-8
"""测试 qy.stdlib.module 模块。."""

from __future__ import annotations

import pytest

from qy.reader import Symbol
from qy.stdlib.module import StandardModule


def test_standard_module_creation():
    """测试创建 StandardModule。."""
    exports = {Symbol("x"): 42, Symbol("y"): "hello"}
    module = StandardModule("test.module", exports)

    assert module.name == "test.module"
    assert module.exports == exports
    assert module.macro_exports == {}


def test_standard_module_with_macro_exports():
    """测试创建带宏导出的 StandardModule。."""
    exports = {Symbol("x"): 42}
    macro_exports = {Symbol("my-macro"): "macro-def"}
    module = StandardModule("test.module", exports, macro_exports)

    assert module.name == "test.module"
    assert module.exports == exports
    assert module.macro_exports == macro_exports


def test_standard_module_resolve():
    """测试解析模块导出。."""
    exports = {Symbol("x"): 42, Symbol("y"): "hello"}
    module = StandardModule("test.module", exports)

    assert module.resolve(Symbol("x")) == 42
    assert module.resolve(Symbol("y")) == "hello"


def test_standard_module_resolve_missing():
    """测试解析不存在的导出抛出异常。."""
    exports = {Symbol("x"): 42}
    module = StandardModule("test.module", exports)

    with pytest.raises(KeyError) as exc_info:
        module.resolve(Symbol("missing"))

    assert "test.module" in str(exc_info.value)
    assert "missing" in str(exc_info.value)
    assert "no export" in str(exc_info.value)


def test_standard_module_resolve_macro():
    """测试解析宏导出。."""
    macro_exports = {Symbol("my-macro"): "macro-def"}
    module = StandardModule("test.module", {}, macro_exports)

    assert module.resolve_macro(Symbol("my-macro")) == "macro-def"


def test_standard_module_resolve_macro_missing():
    """测试解析不存在的宏导出抛出异常。."""
    module = StandardModule("test.module", {})

    with pytest.raises(KeyError) as exc_info:
        module.resolve_macro(Symbol("missing-macro"))

    assert "test.module" in str(exc_info.value)
    assert "missing-macro" in str(exc_info.value)
    assert "no macro export" in str(exc_info.value)


def test_standard_module_empty_exports():
    """测试空导出的模块。."""
    module = StandardModule("empty.module", {})

    assert module.name == "empty.module"
    assert module.exports == {}
    assert module.macro_exports == {}


def test_standard_module_repr():
    """测试模块的字符串表示。."""
    module = StandardModule("test.module", {Symbol("x"): 42})
    repr_str = repr(module)

    assert "StandardModule" in repr_str
    assert "test.module" in repr_str
