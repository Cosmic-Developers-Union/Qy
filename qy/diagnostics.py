# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = ["Diagnostic", "Severity"]

Severity = Literal["error", "warning", "hint"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    message: str
    severity: Severity = "error"
    line: int | None = None
    column: int | None = None
