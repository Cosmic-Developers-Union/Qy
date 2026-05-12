# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass

from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.ir import ProgramIR
from qy.mir import MIRBlockId
from qy.mir import MIRFunction
from qy.mir import MIRInstruction
from qy.mir import MIRProgram
from qy.mir import MIRTerminator
from qy.mir_lowering import lower_mir

__all__ = ["compile_bytecode", "compile_mir_bytecode"]


def compile_bytecode(program: ProgramIR) -> BytecodeProgram:
    return compile_mir_bytecode(lower_mir(program))


def compile_mir_bytecode(program: MIRProgram) -> BytecodeProgram:
    compiler = _BytecodeCompiler(program)
    return compiler.compile()


@dataclass(slots=True)
class _Patch:
    instruction_index: int
    target_block: MIRBlockId


class _FunctionCompiler:
    def __init__(self, function: MIRFunction) -> None:
        self.function = function
        self.instructions: list[Instruction] = []
        self.block_offsets: dict[MIRBlockId, int] = {}
        self.patches: list[_Patch] = []

    def compile(self) -> BytecodeFunction:
        for block in self.function.blocks:
            self.block_offsets[block.id] = len(self.instructions)
            for instruction in block.instructions:
                self.emit_instruction(instruction)
            self.emit_terminator(block.terminator)
        self.patch_jumps()
        return BytecodeFunction(
            self.function.name,
            self.function.params,
            self.function.register_count,
            tuple(self.instructions),
        )

    def emit_instruction(self, instruction: MIRInstruction) -> None:
        self.instructions.append(
            Instruction(instruction.opcode, instruction.operands, instruction.span)
        )

    def emit_terminator(self, terminator: MIRTerminator) -> None:
        match terminator.opcode:
            case "RETURN":
                self.instructions.append(
                    Instruction("RETURN", terminator.operands, terminator.span)
                )
            case "TAIL_CALL":
                self.instructions.append(
                    Instruction("TAIL_CALL", terminator.operands, terminator.span)
                )
            case "JUMP":
                (target_block,) = terminator.operands
                self.patches.append(_Patch(len(self.instructions), _block_id(target_block)))
                self.instructions.append(Instruction("JUMP", (None,), terminator.span))
            case "BRANCH":
                condition, true_block, false_block = terminator.operands
                self.patches.append(_Patch(len(self.instructions), _block_id(false_block)))
                self.instructions.append(
                    Instruction("JUMP_IF_FALSE", (condition, None), terminator.span)
                )
                self.patches.append(_Patch(len(self.instructions), _block_id(true_block)))
                self.instructions.append(Instruction("JUMP", (None,), terminator.span))

    def patch_jumps(self) -> None:
        for patch in self.patches:
            instruction = self.instructions[patch.instruction_index]
            operands = (*instruction.operands[:-1], self.block_offsets[patch.target_block])
            self.instructions[patch.instruction_index] = Instruction(
                instruction.opcode,
                operands,
                instruction.span,
            )


class _BytecodeCompiler:
    def __init__(self, program: MIRProgram) -> None:
        self.program = program

    def compile(self) -> BytecodeProgram:
        return BytecodeProgram(
            tuple(_FunctionCompiler(function).compile() for function in self.program.functions),
            self.program.main,
            self.program.diagnostics,
        )


def _block_id(value: object) -> MIRBlockId:
    if not isinstance(value, int):
        raise TypeError(f"expected MIR block id, got {value!r}")
    return value
