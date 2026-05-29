# coding: utf-8
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.source.span import SourceSpan

__all__ = ["Diagnostic", "Severity"]

Severity = Literal["error", "warning", "hint"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    message: str
    severity: Severity = "error"
    line: int | None = None
    column: int | None = None
    span: SourceSpan | None = None

    @property
    def effective_line(self) -> int | None:
        if self.span is not None:
            return self.span.line
        return self.line

    @property
    def effective_column(self) -> int | None:
        if self.span is not None:
            return self.span.column
        return self.column
