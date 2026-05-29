# coding: utf-8
"""Bytecode 编译器：LIR → Bytecode。.

目标：
- 从 compat LIR 降低到 register VM bytecode
- 纯结构转换，不重新理解语义

注意：
- 此模块只暴露 ``compile_lir_bytecode``，由 ``qy.passes.emit.bytecode`` 在
  pipeline 末段调用。任何"从更早 IR 起步"的捷径（compile_bytecode/HIR→bytecode、
  compile_mir_bytecode/MIR→bytecode）都已删除——必须经由 ``qy.build.pipeline``
  提供的 pipeline 入口逐段降级。
- 仅接受 ``compat`` dialect 的 LIR；``abstract-machine`` dialect 的程序应该走
  另一条后端路径（VM 抽象机直执行或 LLVM）。

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
from qy.diag import Diagnostic
from qy.ir.lir import LIRFunction
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


def _compile_function(function: LIRFunction) -> BytecodeFunction:
    return BytecodeFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(_encode_instruction(i) for i in function.instructions),
    )


def compile_lir_bytecode(program: LIRProgram) -> BytecodeProgram:
    """Compile compat-dialect LIR program to bytecode."""
    if program.dialect != "compat":
        diagnostic = Diagnostic(
            f"compile_lir_bytecode only supports compat LIR, got dialect={program.dialect!r}",
            severity="error",
        )
        return BytecodeProgram((), 0, (*program.diagnostics, diagnostic))
    if not program.ok:
        return BytecodeProgram((), 0, program.diagnostics)
    return BytecodeProgram(
        tuple(_compile_function(f) for f in program.functions),
        program.main,
        program.diagnostics,
    )
