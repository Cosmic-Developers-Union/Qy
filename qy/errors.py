# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/errors/__init__.py

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EvaluationError",
    "QyAggregateError",
    "QyArityError",
    "QyCancelledError",
    "QyCapabilityError",
    "QyEffectError",
    "QyEffectSignal",
    "QyError",
    "QyPythonError",
    "QyResolveError",
    "QyRuntimeError",
    "QySyntaxError",
    "QyTimeoutError",
    "QyTypeError",
    "SourceSpan",
    "TraceFrame",
    "format_qy_error",
]


@dataclass(frozen=True, slots=True)
class SourceSpan:
    source: str | None = None
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None

    @property
    def line(self) -> int | None:
        return self.start_line

    @property
    def column(self) -> int | None:
        return self.start_column

    def format(self) -> str:
        location = self.source or "<source>"
        if self.start_line is None or self.start_column is None:
            return location
        return f"{location}:{self.start_line}:{self.start_column}"


@dataclass(frozen=True, slots=True)
class TraceFrame:
    kind: str
    name: str | None = None
    span: SourceSpan | None = None

    def format(self) -> str:
        label = self.kind if self.name is None else f"{self.kind} {self.name}"
        if self.span is None:
            return f"at {label}"
        return f"at {label} ({self.span.format()})"


class QyError(Exception):
    default_code = "QY_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        span: SourceSpan | None = None,
        frames: tuple[TraceFrame, ...] = (),
        cause: BaseException | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.message = message
        self.span = span
        self.frames = frames
        self.cause = cause
        self.metadata = dict(metadata or {})

    @property
    def line(self) -> int | None:
        return None if self.span is None else self.span.line

    @property
    def column(self) -> int | None:
        return None if self.span is None else self.span.column

    def add_frame(self, frame: TraceFrame) -> None:
        self.frames = (*self.frames, frame)

    def set_span_if_missing(self, span: SourceSpan | None) -> None:
        if self.span is None:
            self.span = span

    def __str__(self) -> str:
        return self.message


class QySyntaxError(QyError):
    default_code = "QY_SYNTAX_ERROR"


class EvaluationError(QyError):
    default_code = "QY_EVALUATION_ERROR"


class QyResolveError(EvaluationError):
    default_code = "QY_UNBOUND_SYMBOL"


class QyTypeError(EvaluationError):
    default_code = "QY_TYPE_ERROR"


class QyArityError(EvaluationError):
    default_code = "QY_ARITY_ERROR"


class QyCapabilityError(EvaluationError):
    default_code = "QY_CAPABILITY_ERROR"


class QyEffectError(EvaluationError):
    default_code = "QY_EFFECT_ERROR"


class QyEffectSignal(QyEffectError):
    default_code = "QY_UNHANDLED_EFFECT"

    def __init__(
        self,
        effect: str,
        arg: object,
        continuation: object,
        *,
        resumable: bool = True,
        span: SourceSpan | None = None,
        cause: BaseException | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            f"unhandled effect {effect!r}",
            span=span,
            cause=cause,
            metadata={
                "effect": effect,
                "arg": arg,
                "resumable": resumable,
                **dict(metadata or {}),
            },
        )
        self.effect = effect
        self.arg = arg
        self.continuation = continuation
        self.resumable = resumable


class QyRuntimeError(EvaluationError):
    default_code = "QY_RUNTIME_ERROR"


class QyPythonError(EvaluationError):
    default_code = "QY_PYTHON_ERROR"


class QyCancelledError(EvaluationError):
    default_code = "QY_CANCELLED"


class QyTimeoutError(EvaluationError):
    default_code = "QY_TIMEOUT"


class QyAggregateError(EvaluationError):
    default_code = "QY_AGGREGATE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        errors: tuple[QyError, ...],
        span: SourceSpan | None = None,
        frames: tuple[TraceFrame, ...] = (),
        cause: BaseException | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            span=span,
            frames=frames,
            cause=cause or (errors[0] if errors else None),
            metadata={"errors": errors, **dict(metadata or {})},
        )
        self.errors = errors


def format_qy_error(error: QyError, *, debug: bool = False) -> str:
    lines = [f"{error.code}: {error.message}"]
    if isinstance(error, QyEffectSignal):
        lines.append(f"effect: {error.effect}")
    if error.span is not None:
        lines.append(f"span: {error.span.format()}")
    if error.frames:
        lines.append("Qy stack:")
        lines.extend(f"  {frame.format()}" for frame in reversed(error.frames))
    if isinstance(error, QyAggregateError) and error.errors:
        lines.append("Errors:")
        for index, item in enumerate(error.errors, start=1):
            lines.append(f"  {index}. {item.code}: {item.message}")
    python_error = error
    if isinstance(error, QyEffectSignal) and isinstance(error.cause, QyPythonError):
        python_error = error.cause
    if debug and isinstance(python_error, QyPythonError) and python_error.cause is not None:
        lines.append("Python stack:")
        lines.extend(
            traceback.format_exception(
                type(python_error.cause),
                python_error.cause,
                python_error.cause.__traceback__,
            )
        )
    return "\n".join(line.rstrip("\n") for line in lines)
