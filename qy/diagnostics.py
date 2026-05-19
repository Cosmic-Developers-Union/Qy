# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/diag/diagnostic.py

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
