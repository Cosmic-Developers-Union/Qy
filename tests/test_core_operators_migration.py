# coding: utf-8
"""测试算子模块迁移到 qy.core 后的功能。."""

from __future__ import annotations

import pytest

from qy.core import Arity
from qy.core import ControlOperator
from qy.core import EffectOperator
from qy.core import EffectSpec
from qy.core import MetaOperator
from qy.core import OperatorSignature
from qy.core import PureOperator
from qy.core import RuntimeOperatorSemantics
from qy.core import ScopeOperator
from qy.core import format_arity_message
from qy.core import lookup_operator_signature
from qy.core import operator_uses_raw_args
from qy.core import runtime_operator_semantics
from qy.core import validate_operator_arity
from qy.errors import QyArityError


def test_import_operators_from_core():
    """测试可以从 qy.core 导入所有算子类型。."""
    assert PureOperator is not None
    assert ScopeOperator is not None
    assert ControlOperator is not None
    assert EffectOperator is not None
    assert MetaOperator is not None


def test_import_operator_signature_from_core():
    """测试可以从 qy.core 导入算子签名相关类型。."""
    assert OperatorSignature is not None
    assert Arity is not None
    assert EffectSpec is not None
    assert lookup_operator_signature is not None
    assert format_arity_message is not None


def test_import_operator_runtime_from_core():
    """测试可以从 qy.core 导入算子运行时相关类型。."""
    assert RuntimeOperatorSemantics is not None
    assert runtime_operator_semantics is not None
    assert operator_uses_raw_args is not None
    assert validate_operator_arity is not None


def test_pure_operator_creation():
    """测试创建纯算子。."""
    def add(x: object, y: object) -> object:
        return int(x) + int(y)  # type: ignore

    op = PureOperator("add", add, "加法算子")
    assert op.name == "add"
    assert op.doc == "加法算子"
    assert op.kind == "pure"
    assert op(2, 3) == 5


def test_operator_signature_arity():
    """测试算子签名的参数数量检查。."""
    arity = Arity(min=1, max=3)
    assert arity.accepts(1)
    assert arity.accepts(2)
    assert arity.accepts(3)
    assert not arity.accepts(0)
    assert not arity.accepts(4)


def test_operator_signature_lookup():
    """测试查找核心算子签名。."""
    sig = lookup_operator_signature("define")
    assert sig is not None
    assert sig.arity.min == 2
    assert sig.arity.max == 2


def test_runtime_operator_semantics():
    """测试运行时算子语义分析。."""
    def dummy_func(x: object) -> object:
        return x

    pure_op = PureOperator("test", dummy_func)
    semantics = runtime_operator_semantics(pure_op)
    assert semantics.dispatch_kind == "pure"
    assert semantics.argument_mode == "eager"


def test_operator_uses_raw_args():
    """测试判断算子是否使用原始参数。."""
    def dummy_func(x: object) -> object:
        return x

    pure_op = PureOperator("test", dummy_func)
    assert not operator_uses_raw_args(pure_op)

    def control_func(args: tuple[object, ...], env: object) -> object:
        return args[0]

    control_op = ControlOperator("test-control", control_func)  # type: ignore
    assert operator_uses_raw_args(control_op)


def test_validate_operator_arity_success():
    """测试算子参数数量验证成功。."""
    def dummy_func(x: object, y: object) -> object:
        return x

    sig = OperatorSignature("any", Arity(2, 2))
    op = PureOperator("test", dummy_func, signature=sig)
    validate_operator_arity(op, 2)


def test_validate_operator_arity_failure():
    """测试算子参数数量验证失败。."""
    def dummy_func(x: object, y: object) -> object:
        return x

    sig = OperatorSignature("any", Arity(2, 2))
    op = PureOperator("test", dummy_func, signature=sig)

    with pytest.raises(QyArityError) as exc_info:
        validate_operator_arity(op, 3)

    assert "expects exactly 2 arguments, got 3" in str(exc_info.value)


def test_format_arity_message():
    """测试格式化参数数量错误消息。."""
    sig = OperatorSignature("any", Arity(2, 2))
    msg = format_arity_message("test", sig, 3)
    assert msg == "test expects exactly 2 arguments, got 3"

    sig2 = OperatorSignature("any", Arity(1, 3))
    msg2 = format_arity_message("test", sig2, 4)
    assert msg2 == "test expects between 1 and 3 arguments, got 4"

    sig3 = OperatorSignature("any", Arity(1, None))
    msg3 = format_arity_message("test", sig3, 0)
    assert msg3 == "test expects at least 1 arguments, got 0"


def test_effect_spec():
    """测试 Effect 规格。."""
    spec = EffectSpec("test-effect", resumable=True)
    assert spec.name == "test-effect"
    assert spec.resumable is True


def test_operator_signature_with_effects():
    """测试带有 Effect 的算子签名。."""
    sig = OperatorSignature(
        "any",
        Arity(1, 2),
        effects=(EffectSpec("test-effect", resumable=False),),
    )
    assert len(sig.effects) == 1
    assert sig.effects[0].name == "test-effect"
    assert sig.effects[0].resumable is False


def test_custom_argument_evaluator():
    """测试自定义参数求值器。."""
    def custom_evaluator(args: tuple[object, ...], env: object) -> object:
        return args

    def dummy_func(*args: object) -> object:
        return args

    op = PureOperator("test", dummy_func, argument_evaluator=custom_evaluator)
    semantics = runtime_operator_semantics(op)
    assert semantics.argument_mode == "custom"


def test_scope_operator():
    """测试作用域算子。."""
    def scope_func(args: tuple[object, ...], env: object) -> object:
        return len(args)

    op = ScopeOperator("test-scope", scope_func, "测试作用域算子")  # type: ignore
    assert op.name == "test-scope"
    assert op.kind == "scope"
    assert op.doc == "测试作用域算子"


def test_effect_operator():
    """测试 Effect 算子。."""
    def effect_func(args: tuple[object, ...], env: object) -> object:
        return args[0]

    op = EffectOperator("test-effect", effect_func, "测试 Effect 算子")  # type: ignore
    assert op.name == "test-effect"
    assert op.kind == "effect"
    assert op.doc == "测试 Effect 算子"


def test_meta_operator():
    """测试元算子。."""
    def meta_func(expression: tuple[object, ...], env: object) -> object:
        return expression

    op = MetaOperator("test-meta", meta_func, "测试元算子")  # type: ignore
    assert op.name == "test-meta"
    assert op.kind == "meta"
    assert op.doc == "测试元算子"
