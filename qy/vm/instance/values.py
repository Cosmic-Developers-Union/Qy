# coding: utf-8
"""VM instance runtime values.

This module defines runtime values specific to VM execution, not part of the
semantic model. These are implementation details used by the register VM and
eval_runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["HostObjectRef", "TailCall"]


@dataclass(frozen=True, slots=True, eq=False)
class HostObjectRef:
    """Reference to a host (Python) object.

    Wraps a Python object so it can be passed through Qy runtime without
    being interpreted as a Qy value. Used for FFI and embedding scenarios.
    """

    value: object


@dataclass(frozen=True, slots=True)
class TailCall:
    """Internal marker for tail call optimization.

    Used by eval_runtime to implement tail call elimination. When a function
    body evaluation returns a TailCall, the interpreter loops instead of
    recursing.
    """

    function: object
    args: tuple[object, ...]
