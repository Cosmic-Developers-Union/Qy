# coding: utf-8
"""测试 qy.vm.instance 模块中的虚拟栈。."""

from __future__ import annotations

from qy.errors import SourceSpan
from qy.vm.instance.frame import VirtualStackFrame
from qy.vm.instance.state import VirtualStack


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


def test_virtual_stack_frame_context_manager():
    """测试 frame 上下文管理器。."""
    stack = VirtualStack()
    span = SourceSpan("test.qy", 1, 1, 1, 10)
    frame = VirtualStackFrame(kind="function", name="test", span=span)

    assert len(stack._frames) == 0

    with stack.frame(frame):
        assert len(stack._frames) == 1
        assert stack._frames[0] == frame

    assert len(stack._frames) == 0


def test_virtual_stack_frame_context_manager_with_exception():
    """测试 frame 上下文管理器在异常时也会正确清理。."""
    stack = VirtualStack()
    span = SourceSpan("test.qy", 1, 1, 1, 10)
    frame = VirtualStackFrame(kind="function", name="test", span=span)

    assert len(stack._frames) == 0

    try:
        with stack.frame(frame):
            assert len(stack._frames) == 1
            raise ValueError("test exception")
    except ValueError:
        pass

    assert len(stack._frames) == 0


def test_virtual_stack_trace():
    """测试 trace 方法生成 TraceFrame 元组。."""
    stack = VirtualStack()
    span1 = SourceSpan("test.qy", 1, 1, 1, 10)
    span2 = SourceSpan("test.qy", 2, 1, 2, 10)
    frame1 = VirtualStackFrame(kind="function", name="frame1", span=span1)
    frame2 = VirtualStackFrame(kind="call", name="frame2", span=span2)

    stack.push(frame1)
    stack.push(frame2)

    trace = stack.trace()
    assert len(trace) == 2
    assert trace[0].kind == "function"
    assert trace[0].name == "frame1"
    assert trace[0].span == span1
    assert trace[1].kind == "call"
    assert trace[1].name == "frame2"
    assert trace[1].span == span2


def test_virtual_stack_trace_empty():
    """测试空栈的 trace 返回空元组。."""
    stack = VirtualStack()
    trace = stack.trace()
    assert trace == ()


def test_virtual_stack_frame_to_trace_frame():
    """测试 VirtualStackFrame.to_trace_frame 方法。."""
    span = SourceSpan("test.qy", 1, 1, 1, 10)
    frame = VirtualStackFrame(kind="lambda", name="test_func", span=span)

    trace_frame = frame.to_trace_frame()
    assert trace_frame.kind == "lambda"
    assert trace_frame.name == "test_func"
    assert trace_frame.span == span


def test_virtual_stack_frame_without_name_and_span():
    """测试创建没有 name 和 span 的 VirtualStackFrame。."""
    frame = VirtualStackFrame(kind="call")

    assert frame.kind == "call"
    assert frame.name is None
    assert frame.span is None

    trace_frame = frame.to_trace_frame()
    assert trace_frame.kind == "call"
    assert trace_frame.name is None
    assert trace_frame.span is None
