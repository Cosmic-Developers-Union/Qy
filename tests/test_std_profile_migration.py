# coding: utf-8
"""测试算子文档模块迁移到 qy.std.profile 后的功能。."""

from __future__ import annotations

from qy.std.profile import OperatorDoc
from qy.std.profile import OperatorModuleDoc
from qy.std.profile import collect_supported_operators
from qy.std.profile import format_operator_docs


def test_import_profile_from_std():
    """测试可以从 qy.std.profile 导入算子文档相关类型。."""
    assert OperatorDoc is not None
    assert OperatorModuleDoc is not None
    assert collect_supported_operators is not None
    assert format_operator_docs is not None


def test_operator_doc_creation():
    """测试创建算子文档。."""
    doc = OperatorDoc(
        name="test",
        kind="pure",
        kind_label="纯算子",
        doc="测试算子",
    )
    assert doc.name == "test"
    assert doc.kind == "pure"
    assert doc.kind_label == "纯算子"
    assert doc.doc == "测试算子"


def test_operator_module_doc_creation():
    """测试创建算子模块文档。."""
    op_doc = OperatorDoc(
        name="test",
        kind="pure",
        kind_label="纯算子",
        doc="测试算子",
    )
    module_doc = OperatorModuleDoc(
        module_name="test.module",
        title="测试模块",
        operators=(op_doc,),
    )
    assert module_doc.module_name == "test.module"
    assert module_doc.title == "测试模块"
    assert len(module_doc.operators) == 1
    assert module_doc.operators[0].name == "test"


def test_collect_supported_operators():
    """测试收集支持的算子。."""
    groups = collect_supported_operators()
    assert len(groups) > 0

    # 应该包含 qy.core 模块
    core_group = next((g for g in groups if g.module_name == "qy.core"), None)
    assert core_group is not None
    assert core_group.title == "内建算子"
    assert len(core_group.operators) > 0

    # 检查一些核心算子是否存在
    operator_names = {op.name for op in core_group.operators}
    assert "define" in operator_names
    assert "lambda" in operator_names
    assert "let" in operator_names


def test_format_operator_docs():
    """测试格式化算子文档。."""
    docs = format_operator_docs()
    assert isinstance(docs, str)
    assert "# Qy 支持的算子" in docs
    assert "## 内建算子" in docs
    assert "模块：`qy.core`" in docs
    assert "`define`" in docs
    assert "`lambda`" in docs


def test_format_operator_docs_with_custom_groups():
    """测试使用自定义分组格式化算子文档。."""
    op_doc = OperatorDoc(
        name="custom-op",
        kind="pure",
        kind_label="纯算子",
        doc="自定义算子",
    )
    module_doc = OperatorModuleDoc(
        module_name="custom.module",
        title="自定义模块",
        operators=(op_doc,),
    )

    docs = format_operator_docs([module_doc])
    assert "# Qy 支持的算子" in docs
    assert "## 自定义模块" in docs
    assert "模块：`custom.module`" in docs
    assert "`custom-op` - 纯算子：自定义算子" in docs


def test_operator_doc_without_description():
    """测试没有描述的算子文档。."""
    op_doc = OperatorDoc(
        name="test",
        kind="pure",
        kind_label="纯算子",
        doc="",
    )
    module_doc = OperatorModuleDoc(
        module_name="test.module",
        title="测试模块",
        operators=(op_doc,),
    )

    docs = format_operator_docs([module_doc])
    # 没有描述时，不应该有冒号
    assert "`test` - 纯算子\n" in docs


def test_collect_operators_sorted_by_name():
    """测试收集的算子按名称排序。."""
    groups = collect_supported_operators()

    for group in groups:
        names = [op.name for op in group.operators]
        assert names == sorted(names), f"Operators in {group.module_name} are not sorted"


def test_operator_kinds_have_labels():
    """测试所有算子类型都有对应的标签。."""
    groups = collect_supported_operators()

    for group in groups:
        for op in group.operators:
            assert op.kind_label, f"Operator {op.name} has no kind label"
            # 检查标签是否是预期的中文标签
            assert op.kind_label in [
                "纯算子",
                "作用域算子",
                "控制算子",
                "Effect 算子",
                "元算子",
                "Effect 定义",
            ], f"Unexpected kind label: {op.kind_label}"
