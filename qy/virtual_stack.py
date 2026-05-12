# coding: utf-8

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from qy.errors import SourceSpan
from qy.errors import TraceFrame

__all__ = [
    "TailCall",
    "VirtualStack",
    "VirtualStackFrame",
]


@dataclass(frozen=True, slots=True)
class VirtualStackFrame:
    kind: str
    name: str | None = None
    span: SourceSpan | None = None

    def to_trace_frame(self) -> TraceFrame:
        return TraceFrame(self.kind, self.name, self.span)


@dataclass(frozen=True, slots=True)
class TailCall:
    target: object
    args: tuple[object, ...]
    span: SourceSpan | None = None


class VirtualStack:
    def __init__(self) -> None:
        self._frames: list[VirtualStackFrame] = []

    @contextmanager
    def frame(self, frame: VirtualStackFrame) -> Iterator[None]:
        self.push(frame)
        try:
            yield
        finally:
            self.pop()

    def push(self, frame: VirtualStackFrame) -> None:
        self._frames.append(frame)

    def replace_top(self, frame: VirtualStackFrame) -> None:
        if not self._frames:
            self.push(frame)
            return
        self._frames[-1] = frame

    def pop(self) -> None:
        if self._frames:
            self._frames.pop()

    def trace(self) -> tuple[TraceFrame, ...]:
        return tuple(frame.to_trace_frame() for frame in self._frames)
