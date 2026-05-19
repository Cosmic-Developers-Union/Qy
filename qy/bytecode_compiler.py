# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/backend/vm/emit.py

from __future__ import annotations

from typing import cast

from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.bytecode import Opcode
from qy.ir import ProgramIR
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRProgram
from qy.passes.lower_lir import lower_lir
from qy.ir.mir import MIRProgram
from qy.passes.lower_mir import lower_mir

__all__ = ["compile_bytecode", "compile_lir_bytecode", "compile_mir_bytecode"]


def compile_bytecode(program: ProgramIR) -> BytecodeProgram:
    return compile_mir_bytecode(lower_mir(program))


def compile_mir_bytecode(program: MIRProgram) -> BytecodeProgram:
    lir = lower_lir(program)
    return compile_lir_bytecode(lir)


def _lir_to_bytecode_opcode(opcode: str) -> Opcode:
    """Map LIR opcodes to bytecode opcodes.

    LIR-specific opcodes are lowered to their bytecode equivalents:
    - LOAD_NIL -> LOAD_HOST with QY_NIL value
    - LOAD_T   -> LOAD_HOST with QY_T value
    - BRANCH_NIL -> JUMP_IF_FALSE (same semantics now that truth is nil-only)
    """
    if opcode == "LOAD_NIL":
        return "LOAD_HOST"
    if opcode == "LOAD_T":
        return "LOAD_HOST"
    if opcode == "BRANCH_NIL":
        return "JUMP_IF_FALSE"
    return cast(Opcode, opcode)


def _lir_to_bytecode_operands(opcode: str, operands: tuple[object, ...]) -> tuple[object, ...]:
    """Adjust operands when mapping LIR opcodes to bytecode opcodes."""
    if opcode == "LOAD_NIL":
        # LOAD_NIL r -> LOAD_HOST r, QY_NIL
        from qy.values import QY_NIL

        return (operands[0], QY_NIL)
    if opcode == "LOAD_T":
        # LOAD_T r -> LOAD_HOST r, QY_T
        from qy.values import QY_T

        return (operands[0], QY_T)
    return operands


def _encode_instruction(instruction: LIRInstruction) -> Instruction:
    opcode = _lir_to_bytecode_opcode(instruction.opcode)
    operands = _lir_to_bytecode_operands(instruction.opcode, instruction.operands)
    return Instruction(opcode, operands, instruction.span)


def compile_lir_bytecode(program: LIRProgram) -> BytecodeProgram:
    if not program.ok:
        return BytecodeProgram((), 0, program.diagnostics)
    if program.dialect != "compat":
        from qy.diag import Diagnostic

        return BytecodeProgram(
            (),
            0,
            (
                *program.diagnostics,
                Diagnostic(
                    "bytecode compiler only supports compat LIR; abstract-machine LIR "
                    "must be lowered through the new LIR encoding path",
                    severity="error",
                ),
            ),
        )
    return BytecodeProgram(
        tuple(
            BytecodeFunction(
                f.name,
                f.params,
                f.register_count,
                tuple(_encode_instruction(i) for i in f.instructions),
            )
            for f in program.functions
        ),
        program.main,
        program.diagnostics,
    )
