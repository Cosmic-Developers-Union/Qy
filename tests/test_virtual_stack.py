# coding: utf-8
"""测试 qy.virtual_stack 模块。."""

from __future__ import annotations

from qy.errors import SourceSpan
from qy.virtual_stack import VirtualStack
from qy.virtual_stack import VirtualStackFrame


def test_virtual_stack_push():
    """测试 push 操作。."""
    stack = VirtualStack()
    span = SourceSpan("test.qy", 1, 1, 1, 10)
    frame = VirtualStackFrame(kind="function", name="test", span=span)

    stack.push(frame)
    assert len(stack._frames) == 1
    assert stack._frames[0] == frame


def test_virtual_stack_replace_top_with_frames():
    """测试 replace_top 替换栈顶。."""
    stack = VirtualStack()
    span1 = SourceSpan("test.qy", 1, 1, 1, 10)
    span2 = SourceSpan("test.qy", 2, 1, 2, 10)
    frame1 = VirtualStackFrame(kind="function", name="frame1", span=span1)
    frame2 = VirtualStackFrame(kind="function", name="frame2", span=span2)

    stack.push(frame1)
    stack.replace_top(frame2)

    assert len(stack._frames) == 1
    assert stack._frames[0] == frame2


def test_virtual_stack_replace_top_empty_stack():
    """测试 replace_top 在空栈时执行 push。."""
    stack = VirtualStack()
    span = SourceSpan("test.qy", 1, 1, 1, 10)
    frame = VirtualStackFrame(kind="function", name="test", span=span)

    stack.replace_top(frame)

    assert len(stack._frames) == 1
    assert stack._frames[0] == frame


def test_virtual_stack_pop():
    """测试 pop 操作。."""
    stack = VirtualStack()
    span = SourceSpan("test.qy", 1, 1, 1, 10)
    frame = VirtualStackFrame(kind="function", name="test", span=span)

    stack.push(frame)
    stack.pop()

    assert len(stack._frames) == 0


def test_virtual_stack_pop_empty():
    """测试 pop 空栈不报错。."""
    stack = VirtualStack()
    stack.pop()  # 不应该抛出异常
    assert len(stack._frames) == 0


def test_virtual_stack_frames():
    """测试访问内部 frames 列表。."""
    stack = VirtualStack()
    span1 = SourceSpan("test.qy", 1, 1, 1, 10)
    span2 = SourceSpan("test.qy", 2, 1, 2, 10)
    frame1 = VirtualStackFrame(kind="function", name="frame1", span=span1)
    frame2 = VirtualStackFrame(kind="function", name="frame2", span=span2)

    stack.push(frame1)
    stack.push(frame2)

    assert len(stack._frames) == 2
    assert stack._frames[0] == frame1
    assert stack._frames[1] == frame2
