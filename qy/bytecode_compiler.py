# coding: utf-8

from __future__ import annotations

from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.ir import ProgramIR
from qy.lir import LIRProgram
from qy.lir_lowering import lower_lir
from qy.mir import MIRProgram
from qy.mir_lowering import lower_mir

__all__ = ["compile_bytecode", "compile_lir_bytecode", "compile_mir_bytecode"]


def compile_bytecode(program: ProgramIR) -> BytecodeProgram:
    return compile_mir_bytecode(lower_mir(program))


def compile_mir_bytecode(program: MIRProgram) -> BytecodeProgram:
    lir = lower_lir(program)
    return compile_lir_bytecode(lir)


def compile_lir_bytecode(program: LIRProgram) -> BytecodeProgram:
    if not program.ok:
        return BytecodeProgram((), 0, program.diagnostics)
    return BytecodeProgram(
        tuple(
            BytecodeFunction(
                f.name,
                f.params,
                f.register_count,
                tuple(Instruction(i.opcode, i.operands, i.span) for i in f.instructions),
            )
            for f in program.functions
        ),
        program.main,
        program.diagnostics,
    )
