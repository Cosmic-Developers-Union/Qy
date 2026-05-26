# coding: utf-8
"""lir.lower pass — MIR → LIR lowering。.

将 MIR 降到 LIR abstract machine IR，含 instruction selection、layout、ABI、
virtual stack、continuation frame、peephole。
"""

from __future__ import annotations

from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.ir.mir import verify_mir
from qy.passes.lir.compact import compact_registers
from qy.passes.lir.compat_effects import lower_compat_effects
from qy.passes.lir.linearize import linearize_function
from qy.passes.lir.peephole import peephole

__all__ = ["_peephole", "lower_lir"]


def lower_lir(program: MIRProgram) -> LIRProgram:
    verifier_diagnostics = verify_mir(program)
    diagnostics = (*program.diagnostics, *verifier_diagnostics)
    if any(d.severity == "error" for d in diagnostics):
        return LIRProgram((), 0, diagnostics)
    return LIRProgram(
        tuple(_lower_function(f, program.constants) for f in program.functions),
        program.main,
        diagnostics,
    )


def _lower_function(function: MIRFunction, constants: MIRConstantPool) -> LIRFunction:
    instructions = linearize_function(function, constants)
    instructions = lower_compat_effects(instructions)
    instructions = peephole(instructions)
    instructions, register_count = compact_registers(
        function.params,
        instructions,
        function.register_count,
    )
    return LIRFunction(
        function.name,
        function.params,
        register_count,
        tuple(instructions),
    )


_peephole = peephole
