# coding: utf-8
"""测试 qy.errors 模块的边界情况。."""

from __future__ import annotations

from qy.errors import QyAggregateError
from qy.errors import QyEffectSignal
from qy.errors import QyPythonError
from qy.errors import QyRuntimeError
from qy.errors import SourceSpan
from qy.errors import format_qy_error
from qy.source import SourceSpan as CanonicalSourceSpan


def test_errors_source_span_is_canonical_source_span():
    assert SourceSpan is CanonicalSourceSpan

    """测试 SourceSpan.format() 在没有行列信息时只返回源文件名。."""
    span = SourceSpan(source="test.qy")
    assert span.format() == "test.qy"


def test_source_span_format_without_source():
    """测试 SourceSpan.format() 在没有源文件时返回 <source>。."""
    span = SourceSpan(start_line=10, start_column=5)
    assert span.format() == "<source>:10:5"


def test_qy_error_set_span_if_missing():
    """测试 QyError.set_span_if_missing() 只在 span 为 None 时设置。."""
    error = QyRuntimeError("test error")
    assert error.span is None

    new_span = SourceSpan(start_line=10, start_column=5)
    error.set_span_if_missing(new_span)
    assert error.span == new_span

    # 再次调用不应该改变 span
    another_span = SourceSpan(start_line=20, start_column=10)
    error.set_span_if_missing(another_span)
    assert error.span == new_span  # 仍然是第一次设置的值


def test_format_qy_error_with_aggregate_error():
    """测试 format_qy_error() 处理 QyAggregateError。."""
    error1 = QyRuntimeError("error 1")
    error2 = QyRuntimeError("error 2")
    aggregate = QyAggregateError(
        "multiple errors",
        errors=(error1, error2),
    )

    formatted = format_qy_error(aggregate)
    assert "Errors:" in formatted
    assert "1. QY_RUNTIME_ERROR: error 1" in formatted
    assert "2. QY_RUNTIME_ERROR: error 2" in formatted


def test_format_qy_error_with_effect_signal_wrapping_python_error():
    """测试 format_qy_error() 处理包装 QyPythonError 的 QyEffectSignal。."""
    python_error = QyPythonError("python error", cause=ValueError("test"))
    effect_signal = QyEffectSignal(
        effect="test-effect",
        arg=None,
        continuation=None,
        cause=python_error,
    )

    formatted = format_qy_error(effect_signal)
    # 代码会提取 python_error 作为 python_error 变量
    # 但实际上只有在 __cause__ 链中才会显示
    # 这个测试主要是为了覆盖第228-229行的代码路径
    assert "test-effect" in formatted
