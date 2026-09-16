# coding: utf-8
"""control.cfg_simplify pass。.

Simplifies MIR control flow graphs:
- Remove unreachable blocks
- Merge linear blocks (single predecessor → single successor)
- Thread jumps through empty blocks
- Renumber block IDs
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRBlockId
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.ir.mir import terminator_target_positions
from qy.ir.mir import terminator_targets
from qy.passes.optimize.facts import rebuild_program
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["CFGSimplifyPass"]


class CFGSimplifyPass(Pass):
    def __init__(self):
        super().__init__("control.cfg_simplify")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_simplify_function(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=rebuild_program(program, functions=new_functions, constants=program.constants),
        )


def _simplify_function(function: MIRFunction) -> MIRFunction:
    blocks = {b.id: b for b in function.blocks}
    entry = function.entry

    reachable = _find_reachable(entry, blocks)
    blocks = {bid: b for bid, b in blocks.items() if bid in reachable}

    if not blocks:
        return function

    blocks = _thread_jumps(blocks)

    reachable = _find_reachable(entry, blocks)
    blocks = {bid: b for bid, b in blocks.items() if bid in reachable}

    blocks = _merge_linear(blocks, entry)

    id_map: dict[MIRBlockId, MIRBlockId] = {}
    for new_id, old_id in enumerate(sorted(blocks.keys())):
        id_map[old_id] = new_id

    new_blocks = tuple(
        MIRBlock(
            id_map[b.id],
            b.instructions,
            _remap_terminator(b.terminator, id_map),
        )
        for b in (blocks[bid] for bid in sorted(blocks.keys()))
    )

    return MIRFunction(
        function.name,
        function.params,
        function.register_count,
        new_blocks,
        id_map.get(entry, 0),
    )


def _find_reachable(entry: MIRBlockId, blocks: dict[MIRBlockId, MIRBlock]) -> set[MIRBlockId]:
    visited: set[MIRBlockId] = set()
    stack = [entry]
    while stack:
        bid = stack.pop()
        if bid in visited:
            continue
        visited.add(bid)
        block = blocks.get(bid)
        if block is None:
            continue
        for succ in _successors(block.terminator):
            stack.append(succ)
    return visited


def _successors(terminator: MIRTerminator) -> list[MIRBlockId]:
    """CFG 后继：直接复用 `qy.ir.mir` 的 terminator 目标语义。。.

    这里必须包含 ``EFFECT_PERFORM`` 的 resume 边，否则含 ``perform`` 的函数
    会把 resume 块当成不可达并删掉（历史上 effect 用例就是这样被破坏的）。
    """
    return terminator_targets(terminator)


def _thread_jumps(blocks: dict[MIRBlockId, MIRBlock]) -> dict[MIRBlockId, MIRBlock]:
    def resolve_target(bid: MIRBlockId, seen: set[MIRBlockId]) -> MIRBlockId:
        if bid in seen or bid not in blocks:
            return bid
        block = blocks[bid]
        if block.instructions == () and block.terminator.opcode == "JUMP":
            seen.add(bid)
            return resolve_target(cast(int, block.terminator.operands[0]), seen)
        return bid

    result: dict[MIRBlockId, MIRBlock] = {}
    for bid, block in blocks.items():
        terminator = block.terminator
        match terminator.opcode:
            case "JUMP":
                target = resolve_target(cast(int, terminator.operands[0]), {bid})
                terminator = MIRTerminator("JUMP", (target,), terminator.span)
            case "BRANCH":
                cond, true_b, false_b = terminator.operands
                true_b = resolve_target(cast(int, true_b), {bid})
                false_b = resolve_target(cast(int, false_b), {bid})
                terminator = MIRTerminator("BRANCH", (cond, true_b, false_b), terminator.span)
        result[bid] = MIRBlock(bid, block.instructions, terminator)
    return result


def _merge_linear(
    blocks: dict[MIRBlockId, MIRBlock], entry: MIRBlockId
) -> dict[MIRBlockId, MIRBlock]:
    predecessors: dict[MIRBlockId, list[MIRBlockId]] = {bid: [] for bid in blocks}
    for bid, block in blocks.items():
        for succ in _successors(block.terminator):
            if succ in predecessors:
                predecessors[succ].append(bid)

    changed = True
    while changed:
        changed = False
        for bid in list(blocks.keys()):
            if bid not in blocks:
                continue
            block = blocks[bid]
            if block.terminator.opcode != "JUMP":
                continue
            succ_id = cast(int, block.terminator.operands[0])
            if succ_id not in blocks or succ_id == bid:
                continue
            if len(predecessors.get(succ_id, [])) != 1:
                continue
            if succ_id == entry:
                continue
            succ = blocks[succ_id]
            merged = MIRBlock(
                bid,
                (*block.instructions, *succ.instructions),
                succ.terminator,
            )
            blocks[bid] = merged
            del blocks[succ_id]
            for s in _successors(succ.terminator):
                if s in predecessors:
                    predecessors[s] = [bid if p == succ_id else p for p in predecessors[s]]
            del predecessors[succ_id]
            changed = True
            break

    return blocks


def _remap_terminator(
    terminator: MIRTerminator, id_map: dict[MIRBlockId, MIRBlockId]
) -> MIRTerminator:
    """按 id_map 重写 terminator 的全部 block 目标操作数。.

    哪些操作数是 block 目标由 `qy.ir.mir.terminator_target_positions` 给出，
    因此 ``EFFECT_PERFORM`` 的 resume 块也会被正确重映射。
    """
    positions = terminator_target_positions(terminator)
    if not positions:
        return terminator
    operands = list(terminator.operands)
    for index in positions:
        if index < len(operands) and isinstance(operands[index], int):
            operands[index] = id_map.get(operands[index], operands[index])
    return MIRTerminator(terminator.opcode, tuple(operands), terminator.span)
