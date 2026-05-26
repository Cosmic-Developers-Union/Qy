# coding: utf-8
"""optimize.instr_sched pass.

Instruction scheduling at the LIR level: reorders instructions to reduce
register pressure and improve instruction-level parallelism (ILP), while
preserving data dependencies.

This pass operates on linearized LIR instruction streams (after effect
lowering, before bytecode emission).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["InstructionSchedulePass"]


# Opcodes that have side effects and cannot be reordered past each other
_EFFECTFUL_OPCODES: frozenset[str] = frozenset(
    {
        "STORE_LOCAL",
        "DEFINE_ONCE",
        "CALL",
        "TAIL_CALL",
        "RETURN",
        "HANDLE",
        "PERFORM",
        "RESUME",
        "RAISE_EFFECT",
        "DEFINE_MODULE",
        "FROM_IMPORT",
        "RUNTIME_EVAL",
        "CACHE_EVAL",
        "PARALLEL_GATHER",
        "ALL_GATHER",
        "RACE_FIRST",
        "APPEND_RESULT",
    }
)


class InstructionSchedulePass(Pass):
    def __init__(self):
        super().__init__("optimize.instr_sched")

    def run(self, context: PassContext) -> PassResult:
        program = cast(LIRProgram, context.input_artifact)
        new_functions = tuple(_schedule_function(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=LIRProgram(new_functions, program.main, program.diagnostics, program.dialect),
        )


def _schedule_function(function: LIRFunction) -> LIRFunction:
    """Simple list-scheduling of the instruction stream.

    Groups instructions into basic blocks bounded by side-effectful ops
    and control flow, then reorders within each block to minimize
    register pressure.
    """
    blocks = _split_into_blocks(function.instructions)
    scheduled: list[LIRInstruction] = []

    for block in blocks:
        scheduled.extend(_schedule_block(block))

    return LIRFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(scheduled),
        function.frame_layout,
        function.symbol_spaces,
        function.continuations,
        function.handlers,
    )


@dataclass(slots=True)
class _SchedBlock:
    """A sequence of instructions that can be freely reordered."""

    instructions: list[LIRInstruction]
    fixed: list[LIRInstruction]  # instructions that anchor the block


def _split_into_blocks(
    instructions: tuple[LIRInstruction, ...],
) -> list[list[LIRInstruction]]:
    """Split instructions into reorderable blocks."""
    blocks: list[list[LIRInstruction]] = []
    current: list[LIRInstruction] = []

    for inst in instructions:
        current.append(inst)
        if _is_block_boundary(inst):
            blocks.append(current)
            current = []

    if current:
        blocks.append(current)

    return blocks


def _is_block_boundary(inst: LIRInstruction) -> bool:
    return inst.opcode in _EFFECTFUL_OPCODES or inst.opcode in (
        "JUMP",
        "JUMP_IF_FALSE",
        "BRANCH_NIL",
    )


def _schedule_block(instructions: list[LIRInstruction]) -> list[LIRInstruction]:
    """Reorder instructions to minimize register pressure.

    Simple approach: move loads and pure computations as late as possible
    (closer to their first use), reducing the number of simultaneously
    live registers.
    """
    if len(instructions) <= 1:
        return instructions

    # Compute use-def chains within the block
    def_map: dict[int, int] = {}  # reg -> instruction index that defines it
    uses_per_inst: list[set[int]] = []

    for idx, inst in enumerate(instructions):
        uses: set[int] = set()
        for op in inst.operands:
            if isinstance(op, int):
                uses.add(op)
            elif isinstance(op, tuple):
                for sub in op:
                    if isinstance(sub, int):
                        uses.add(sub)
        uses_per_inst.append(uses)

        # Track definitions
        if inst.operands and isinstance(inst.operands[0], int):
            if inst.opcode not in ("DEFINE_ONCE", "STORE_LOCAL"):
                def_map[inst.operands[0]] = idx

    # Build dependency graph: inst i depends on inst j if i uses a reg defined by j
    deps: list[set[int]] = [set() for _ in instructions]
    for i, uses in enumerate(uses_per_inst):
        for used_reg in uses:
            if used_reg in def_map:
                j = def_map[used_reg]
                if j != i:
                    deps[i].add(j)

    # Topological sort with register-pressure-aware tiebreaking
    return _topo_sort_with_pressure(instructions, deps)


def _topo_sort_with_pressure(
    instructions: list[LIRInstruction],
    deps: list[set[int]],
) -> list[LIRInstruction]:
    """Topological sort that prefers scheduling instructions that free registers."""
    n = len(instructions)
    in_degree = [0] * n
    reverse_deps: list[set[int]] = [set() for _ in range(n)]

    for i in range(n):
        for j in deps[i]:
            reverse_deps[j].add(i)
        in_degree[i] = len(deps[i])

    result: list[LIRInstruction] = []
    ready = [i for i in range(n) if in_degree[i] == 0]

    while ready:
        # Among ready instructions, prefer those whose result is used soonest
        # This reduces live register count
        ready.sort(key=lambda i: _next_use_distance(i, instructions, reverse_deps, n))
        chosen = ready.pop(0)
        result.append(instructions[chosen])

        for dep in reverse_deps[chosen]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                ready.append(dep)

    return result


def _next_use_distance(
    idx: int,
    instructions: list[LIRInstruction],
    reverse_deps: list[set[int]],
    n: int,
) -> int:
    """Estimate how soon the result of instruction *idx* is used."""
    if not reverse_deps[idx]:
        return n  # unused: schedule last
    return min(reverse_deps[idx]) - idx
