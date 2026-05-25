# coding: utf-8
"""Bytecode 编译器：LIR → Bytecode。.

目标：
- 从 LIR 降低到 bytecode
- 纯结构转换，不重新理解语义

注意：
- 此模块只暴露 ``compile_lir_bytecode``，由 ``qy.passes.emit.bytecode`` 在
  pipeline 末段调用。任何"从更早 IR 起步"的捷径（compile_bytecode/HIR→bytecode、
  compile_mir_bytecode/MIR→bytecode）都已删除——必须经由 ``qy.passes.build``
  提供的 pipeline 入口逐段降级。

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
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRProgram

__all__ = ["compile_lir_bytecode"]


def _lir_to_bytecode_opcode(opcode: str) -> Opcode:
    """Map LIR opcodes to bytecode opcodes."""
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
        from qy.core.syntax import nil

        return (operands[0], nil)
    if opcode == "LOAD_T":
        from qy.sem.core import T

        return (operands[0], T)
    return operands


def _encode_instruction(instruction: LIRInstruction) -> Instruction:
    opcode = _lir_to_bytecode_opcode(instruction.opcode)
    operands = _lir_to_bytecode_operands(instruction.opcode, instruction.operands)
    return Instruction(opcode, operands, instruction.span)


def compile_lir_bytecode(program: LIRProgram) -> BytecodeProgram:
    """Compile LIR program to bytecode."""
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
