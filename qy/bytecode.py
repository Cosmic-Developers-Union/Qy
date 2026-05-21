# coding: utf-8
"""Compatibility re-exports for BytecodeFunctionValue.

BytecodeFunctionValue is a VM implementation detail (contains closure).
It remains accessible from qy.bytecode for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram

if TYPE_CHECKING:
    from qy.environment import Environment

__all__ = ["BytecodeFunctionValue"]


@dataclass(frozen=True, slots=True)
class BytecodeFunctionValue:
    """Bytecode function with closure (VM implementation detail).

    This is specific to the Python VM implementation and contains runtime state.
    """

    function: BytecodeFunction
    closure: Environment
    program: BytecodeProgram | None = None
