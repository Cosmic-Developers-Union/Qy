# coding: utf-8
"""Bytecode 编译器：LIR → Bytecode。.

目标：
- 从 LIR 降低到 bytecode
- 纯结构转换，不重新理解语义
- 替代 qy/bytecode_compiler.py

当前：
- 从 qy/bytecode_compiler.py 迁移编译逻辑
- 支持 HIR/MIR/LIR 到 bytecode 的完整管线

禁止：
- 不得重新理解 HIR/MIR 语义
- 不得包含执行逻辑
"""

from __future__ import annotations

from typing import cast

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram
from qy.backend.vm.bytecode import Instruction
from qy.backend.vm.bytecode import Opcode
from qy.ir import ProgramIR
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRProgram
from qy.passes.lower_lir import lower_lir
from qy.passes.lower_mir import lower_mir

__all__ = ["compile_bytecode", "compile_lir_bytecode", "compile_mir_bytecode"]


def compile_bytecode(program: ProgramIR) -> BytecodeProgram:
    """Compile HIR program to bytecode.

    Args:
        program: HIR program

    Returns:
        BytecodeProgram
    """
    return compile_mir_bytecode(lower_mir(program))


def compile_mir_bytecode(program: MIRProgram) -> BytecodeProgram:
    """Compile MIR program to bytecode.

    Args:
        program: MIR program

    Returns:
        BytecodeProgram
    """
    lir = lower_lir(program)
    return compile_lir_bytecode(lir)


def _lir_to_bytecode_opcode(opcode: str) -> Opcode:
    """Map LIR opcodes to bytecode opcodes.

    LIR-specific opcodes are lowered to their bytecode equivalents:
    - LOAD_NIL -> LOAD_HOST with QY_NIL value
    - LOAD_T   -> LOAD_HOST with QY_T value
    - BRANCH_NIL -> JUMP_IF_FALSE (same semantics now that truth is nil-only)

    Args:
        opcode: LIR opcode

    Returns:
        Bytecode opcode
    """
    if opcode == "LOAD_NIL":
        return "LOAD_HOST"
    if opcode == "LOAD_T":
        return "LOAD_HOST"
    if opcode == "BRANCH_NIL":
        return "JUMP_IF_FALSE"
    return cast(Opcode, opcode)


def _lir_to_bytecode_operands(opcode: str, operands: tuple[object, ...]) -> tuple[object, ...]:
    """Adjust operands when mapping LIR opcodes to bytecode opcodes.

    Args:
        opcode: LIR opcode
        operands: LIR operands

    Returns:
        Bytecode operands
    """
    if opcode == "LOAD_NIL":
        # LOAD_NIL r -> LOAD_HOST r, nil
        from qy.core.syntax import nil

        return (operands[0], nil)
    if opcode == "LOAD_T":
        # LOAD_T r -> LOAD_HOST r, T
        from qy.sem.core import T

        return (operands[0], T)
    return operands


def _encode_instruction(instruction: LIRInstruction) -> Instruction:
    """Encode LIR instruction to bytecode instruction.

    Args:
        instruction: LIR instruction

    Returns:
        Bytecode instruction
    """
    opcode = _lir_to_bytecode_opcode(instruction.opcode)
    operands = _lir_to_bytecode_operands(instruction.opcode, instruction.operands)
    return Instruction(opcode, operands, instruction.span)


def compile_lir_bytecode(program: LIRProgram) -> BytecodeProgram:
    """Compile LIR program to bytecode.

    Args:
        program: LIR program

    Returns:
        BytecodeProgram
    """
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
