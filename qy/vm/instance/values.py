# coding: utf-8
"""VM instance runtime values.

This module defines runtime values specific to VM execution, not part of the
semantic model. These are implementation details used by the register VM.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["TailCall"]


@dataclass(frozen=True, slots=True)
class TailCall:
    """Internal marker for tail call optimization.

    When a function body evaluation returns a TailCall, the caller loops
    instead of recursing.
    """

    function: object
    args: tuple[object, ...]
