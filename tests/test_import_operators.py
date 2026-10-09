# coding: utf-8
"""测试 qy.import_.operators 模块的内部函数。."""

from __future__ import annotations

import pytest

from qy.core.syntax import Symbol
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil
from qy.errors import QyTypeError
from qy.import_.module import StandardModule
from qy.import_.operators import _from_import
from qy.import_.operators import _is_special_form
from qy.import_.operators import _parse_export_names
from qy.import_.registry import register_module
from qy.session.runtime_space import create_standard_runtime_space as standard_environment


def test_is_special_form_with_matching_chain():
    """测试 _is_special_form 识别匹配的 chain 形式。."""
    form = list_to_chain([Symbol("exports"), Symbol("x"), Symbol("y")])
    assert _is_special_form(form, "exports") is True


def test_is_special_form_with_non_matching_chain():
    """测试 _is_special_form 拒绝不匹配的 chain。."""
    form = list_to_chain([Symbol("define"), Symbol("x"), Symbol("y")])
    assert _is_special_form(form, "exports") is False


def test_is_special_form_with_nil():
    """测试 _is_special_form 拒绝 nil。."""
    assert _is_special_form(nil, "exports") is False


def test_is_special_form_with_non_chain():
    """测试 _is_special_form 拒绝非 chain。."""
    assert _is_special_form(Symbol("exports"), "exports") is False


def test_is_special_form_with_non_symbol_head():
    """测试 _is_special_form 拒绝非 Symbol 开头的 chain。."""
    form = list_to_chain([42, Symbol("x")])
    assert _is_special_form(form, "exports") is False


def test_parse_export_names_with_symbols():
    """测试 _parse_export_names 解析符号 chain。."""
    items = list_to_chain([Symbol("x"), Symbol("y"), Symbol("z")])
    assert _parse_export_names(items) == [Symbol("x"), Symbol("y"), Symbol("z")]


def test_parse_export_names_with_nested_chain():
    """测试 _parse_export_names 解析嵌套 chain。."""
    inner = list_to_chain([Symbol("y"), Symbol("z")])
    items = list_to_chain([Symbol("x"), inner, Symbol("w")])
    assert _parse_export_names(items) == [Symbol("x"), Symbol("y"), Symbol("z"), Symbol("w")]


def test_parse_export_names_with_empty_chain():
    """测试 _parse_export_names 处理空 chain。."""
    assert _parse_export_names(list_to_chain([])) == []


def test_parse_export_names_with_non_symbol_raises_error():
    """测试 _parse_export_names 拒绝非符号。."""
    items = list_to_chain([Symbol("x"), 42, Symbol("y")])
    with pytest.raises(QyTypeError) as exc_info:
        _parse_export_names(items)
    assert "module export" in str(exc_info.value)


def test_parse_export_names_deeply_nested():
    """测试 _parse_export_names 处理深度嵌套。."""
    d = list_to_chain([Symbol("c"), Symbol("d")])
    c = list_to_chain([Symbol("b"), d])
    items = list_to_chain([Symbol("a"), c])
    assert _parse_export_names(items) == [Symbol("a"), Symbol("b"), Symbol("c"), Symbol("d")]


async def test_from_import_operator_folds_chain_form():
    """验证 from ScopeOperator 消费 chain 形式并真正折叠绑定。."""
    register_module(StandardModule("test.import_ops", {Symbol("answer"): 42}))
    env = standard_environment()
    await _from_import(
        (Symbol("test.import_ops"), Symbol("import"), Symbol("answer")),
        env,
    )
    assert env.resolve(Symbol("answer")) == 42


def test_iter_selected_exports_shared_selection_rules():
    """Fold primitive 单源：runtime 导出 / 宏导出 / 缺失（require 语义）。."""
    from qy.import_.from_fold import iter_selected_exports
    from qy.import_.parse import ImportSpec

    module = StandardModule(
        "m",
        {Symbol("a"): 1, Symbol("b"): 2},
        {Symbol("mac"): "MACRO"},
    )
    specs = (ImportSpec(Symbol("a"), Symbol("x")), ImportSpec(Symbol("mac"), Symbol("y")))
    assert list(iter_selected_exports("m", specs, module)) == [
        (Symbol("x"), 1, False),
        (Symbol("y"), "MACRO", True),
    ]

    from qy.import_.from_fold import missing_export_names

    assert missing_export_names(specs, module) == ()
    missing = (ImportSpec(Symbol("nope"), Symbol("z")),)
    assert missing_export_names(missing, module) == (Symbol("nope"),)
    with pytest.raises(KeyError, match="has no export"):
        list(iter_selected_exports("m", missing, module))
    assert list(iter_selected_exports("m", missing, module, require=False)) == []


def test_package_fold_attribute_is_not_shadowed_by_submodule():
    """`qy.import_.fold` 必须仍是核心 fold 算子函数，不被同名子模块 shadow。."""
    import qy.import_ as import_pkg

    assert callable(import_pkg.fold), "qy.import_.fold must remain the fold operator"
    from qy.import_.from_fold import fold_import

    assert callable(fold_import)
