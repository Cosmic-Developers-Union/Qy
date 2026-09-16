# coding: utf-8
"""optimize.reg_alloc pass.

Register allocation at the MIR level using liveness-based linear scan.

After all MIR transforms, this pass renumbers virtual registers to minimize
the total register count per function.  It uses liveness intervals to
determine which registers can share the same physical slot.
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.ir.mir import register_operand_positions
from qy.ir.mir import register_tuple_positions
from qy.ir.mir import terminator_register_positions
from qy.ir.mir import terminator_register_tuple_positions
from qy.passes.optimize.facts import rebuild_function
from qy.passes.optimize.facts import rebuild_program
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["RegisterAllocationPass"]


class RegisterAllocationPass(Pass):
    def __init__(self):
        super().__init__("optimize.reg_alloc")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_allocate_registers(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=rebuild_program(program, functions=new_functions, constants=program.constants),
        )


def _allocate_registers(function: MIRFunction) -> MIRFunction:
    """Linear scan register allocation.

    Assigns physical register numbers to virtual registers based on
    liveness intervals.  Registers with non-overlapping live ranges
    can share the same physical register.

    槽位约定：LIR 的 ``compact_registers`` 把 ``0..len(params)-1`` 当作参数槽并按
    identity 固定（``register_map = {index: index for index, _ in enumerate(params)}``），
    MIR 层必须保持同一约定，因此这些物理槽在此保留、不再分配给其他虚拟寄存器
    （实测：不保留会让一个语料在 S5 阶段结果不一致）。
    """
    from qy.analysis.liveness import compute_liveness

    info = compute_liveness(function)
    intervals = info.intervals.intervals
    referenced = _referenced_registers(function)

    if not intervals and not referenced:
        return function

    param_count = len(function.params)
    # 0..param_count-1 保持 identity 映射，并保留这些物理槽（与 LIR
    # compact_registers 的参数槽约定一致）。
    reg_to_physical: dict[int, int] = {index: index for index in range(param_count)}
    physical_map: dict[int, int] = {index: 1 << 30 for index in range(param_count)}
    next_physical = param_count

    for vreg in sorted(intervals.keys(), key=lambda r: intervals[r][0]):
        if vreg in reg_to_physical:
            continue
        start, end = intervals[vreg]
        assigned = False
        for preg, last_end in physical_map.items():
            if last_end < start:
                reg_to_physical[vreg] = preg
                physical_map[preg] = end
                assigned = True
                break
        if not assigned:
            reg_to_physical[vreg] = next_physical
            physical_map[next_physical] = end
            next_physical += 1

    # 活跃区间未覆盖的寄存器也必须重编号：否则旧编号会与新的物理编号冲突，
    # 或超出缩减后的 register_count（历史缺陷：LIR 报 out-of-range register）。
    for vreg in sorted(referenced):
        if vreg in reg_to_physical:
            continue
        reg_to_physical[vreg] = next_physical
        next_physical += 1

    new_blocks = tuple(_remap_block(block, reg_to_physical) for block in function.blocks)
    new_register_count = max(next_physical, len(function.params))

    return rebuild_function(function, blocks=new_blocks, register_count=new_register_count)


def _referenced_registers(function: MIRFunction) -> set[int]:
    """函数内出现过的全部虚拟寄存器（指令 + terminator，含寄存器元组）。."""
    from qy.ir.mir import terminator_register_positions
    from qy.ir.mir import terminator_register_tuple_positions

    registers: set[int] = set()

    def _add(value: object) -> None:
        if isinstance(value, int):
            registers.add(value)

    def _add_tuple(value: object) -> None:
        if isinstance(value, tuple):
            for item in value:
                _add(item)

    for block in function.blocks:
        for inst in block.instructions:
            operands = inst.operands
            for index in register_operand_positions(inst):
                if index < len(operands):
                    _add(operands[index])
            for index in register_tuple_positions(inst):
                if index < len(operands):
                    _add_tuple(operands[index])
        terminator = block.terminator
        operands = terminator.operands
        for index in terminator_register_positions(terminator):
            if index < len(operands):
                _add(operands[index])
        for index in terminator_register_tuple_positions(terminator):
            if index < len(operands):
                _add_tuple(operands[index])
    return registers


def _remap_block(block: MIRBlock, reg_map: dict[int, int]) -> MIRBlock:
    """Remap all register references in a block."""
    new_instructions = tuple(_remap_instruction(inst, reg_map) for inst in block.instructions)
    new_terminator = _remap_terminator(block.terminator, reg_map)
    return MIRBlock(block.id, new_instructions, new_terminator)


def _remap_instruction(inst: MIRInstruction, reg_map: dict[int, int]) -> MIRInstruction:
    """按 `qy.ir.mir` 给出的寄存器操作数位置重写指令。."""
    positions = register_operand_positions(inst)
    tuple_positions = register_tuple_positions(inst)
    if not positions and not tuple_positions:
        return inst
    operands = list(inst.operands)
    for index in positions:
        if index < len(operands) and isinstance(operands[index], int):
            operands[index] = reg_map.get(operands[index], operands[index])
    for index in tuple_positions:
        if index >= len(operands):
            continue
        value = operands[index]
        if isinstance(value, tuple):
            operands[index] = tuple(
                reg_map.get(item, item) if isinstance(item, int) else item for item in value
            )
    return MIRInstruction(inst.opcode, tuple(operands), inst.span)


def _remap_terminator(term: MIRTerminator, reg_map: dict[int, int]) -> MIRTerminator:
    """按 `qy.ir.mir` 给出的寄存器操作数位置重写 terminator。."""
    positions = terminator_register_positions(term)
    tuple_positions = terminator_register_tuple_positions(term)
    if not positions and not tuple_positions:
        return term
    operands = list(term.operands)
    for index in positions:
        if index < len(operands) and isinstance(operands[index], int):
            operands[index] = reg_map.get(operands[index], operands[index])
    for index in tuple_positions:
        if index >= len(operands):
            continue
        value = operands[index]
        if isinstance(value, tuple):
            operands[index] = tuple(
                reg_map.get(item, item) if isinstance(item, int) else item for item in value
            )
    return MIRTerminator(term.opcode, tuple(operands), term.span)
