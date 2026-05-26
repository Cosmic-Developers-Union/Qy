# coding: utf-8
"""optimize.licm pass.

Loop-Invariant Code Motion: detects pure operations whose inputs do not
change within a loop body, and hoists them to the loop preheader.

This reduces redundant computation inside hot loops.
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRBlockId
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["LICMPass"]

_HOISTABLE_OPCODES: frozenset[str] = frozenset(
    {
        "LOAD_CONST",
        "LOAD_HOST",
        "LOAD_ENV",
    }
)


class LICMPass(Pass):
    def __init__(self):
        super().__init__("optimize.licm")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_hoist_in_function(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _hoist_in_function(function: MIRFunction) -> MIRFunction:
    """Hoist loop-invariant instructions to preheaders."""
    loops = _find_natural_loops(function)
    if not loops:
        return function

    blocks_map = {b.id: b for b in function.blocks}
    changed = False

    for header_id, body_ids, preheader_id in loops:
        header = blocks_map.get(header_id)
        if header is None:
            continue

        # Collect registers defined inside the loop body
        loop_defs: set[int] = set()
        loop_uses: set[int] = set()
        for bid in body_ids | {header_id}:
            block = blocks_map.get(bid)
            if block is None:
                continue
            for inst in block.instructions:
                dest = _def(inst)
                if dest is not None:
                    loop_defs.add(dest)
                for used in _uses(inst):
                    loop_uses.add(used)

        # Instructions that can be hoisted:
        # - In the loop body (not in header, for simplicity)
        # - Pure (HOISTABLE_OPCODES)
        # - Whose inputs are not defined inside the loop
        preheader = blocks_map.get(preheader_id)
        if preheader is None:
            continue

        hoistable: list[MIRInstruction] = []
        for bid in body_ids:
            block = blocks_map.get(bid)
            if block is None:
                continue
            new_instructions: list[MIRInstruction] = []
            for inst in block.instructions:
                if _is_loop_invariant(inst, loop_defs):
                    dest = _def(inst)
                    if dest is not None and dest not in loop_uses:
                        # No use in the loop after this definition; safe to hoist
                        hoistable.append(inst)
                        changed = True
                        continue
                new_instructions.append(inst)
            blocks_map[bid] = MIRBlock(block.id, tuple(new_instructions), block.terminator)

        if hoistable:
            new_preheader_insts = (*preheader.instructions, *hoistable)
            blocks_map[preheader_id] = MIRBlock(
                preheader.id, tuple(new_preheader_insts), preheader.terminator
            )

    if not changed:
        return function

    new_blocks = tuple(blocks_map[b.id] for b in function.blocks if b.id in blocks_map)

    return MIRFunction(
        function.name,
        function.params,
        function.register_count,
        new_blocks,
        function.entry,
    )


def _is_loop_invariant(inst: MIRInstruction, loop_defs: set[int]) -> bool:
    """Check if *inst*'s computation depends only on values defined outside the loop."""
    if inst.opcode in _HOISTABLE_OPCODES:
        return True
    if inst.opcode == "MOVE":
        src = inst.operands[1]
        if isinstance(src, int) and src not in loop_defs:
            return True
    return False


def _find_natural_loops(
    function: MIRFunction,
) -> list[tuple[MIRBlockId, set[MIRBlockId], MIRBlockId]]:
    """Find natural loops as (header, body, preheader) triples.

    Returns a list of (header_id, body_block_ids, preheader_id).
    """
    blocks_map = {b.id: b for b in function.blocks}
    # Build dominator tree (simple iterative)
    dom = _compute_dominators(function)
    # Find back edges: edges where target dominates source
    back_edges: list[tuple[MIRBlockId, MIRBlockId]] = []
    for block in function.blocks:
        for succ_id in _successors(block.terminator):
            if succ_id in dom.get(block.id, set()):
                back_edges.append((block.id, succ_id))

    loops: list[tuple[MIRBlockId, set[MIRBlockId], MIRBlockId]] = []
    for tail_id, header_id in back_edges:
        body = _compute_loop_body(header_id, tail_id, blocks_map)
        # Find preheader: the block before header that is not in the loop body
        preheader = _find_preheader(header_id, body, blocks_map, function)
        if preheader is not None:
            loops.append((header_id, body, preheader))

    return loops


def _compute_dominators(
    function: MIRFunction,
) -> dict[MIRBlockId, set[MIRBlockId]]:
    """Simple iterative dominator computation."""
    all_ids = {b.id for b in function.blocks}
    dom: dict[MIRBlockId, set[MIRBlockId]] = {b.id: set(all_ids) for b in function.blocks}
    dom[function.entry] = {function.entry}

    changed = True
    while changed:
        changed = False
        for block in function.blocks:
            if block.id == function.entry:
                continue
            preds = _predecessors(block.id, function)
            if not preds:
                continue
            new_dom = set(all_ids)
            for p in preds:
                new_dom &= dom.get(p, set(all_ids))
            new_dom.add(block.id)
            if new_dom != dom[block.id]:
                dom[block.id] = new_dom
                changed = True

    return dom


def _predecessors(block_id: MIRBlockId, function: MIRFunction) -> list[MIRBlockId]:
    preds: list[MIRBlockId] = []
    for block in function.blocks:
        for succ in _successors(block.terminator):
            if succ == block_id:
                preds.append(block.id)
    return preds


def _successors(term: MIRTerminator) -> list[MIRBlockId]:
    match term.opcode:
        case "JUMP":
            return [cast(int, term.operands[0])]
        case "BRANCH":
            _, true_b, false_b = term.operands
            return [cast(int, true_b), cast(int, false_b)]
        case _:
            return []


def _compute_loop_body(
    header_id: MIRBlockId,
    tail_id: MIRBlockId,
    blocks_map: dict[MIRBlockId, MIRBlock],
) -> set[MIRBlockId]:
    """Compute the set of blocks in the loop body by walking backwards from tail to header."""
    body = {header_id}
    worklist = [tail_id]
    while worklist:
        bid = worklist.pop()
        if bid in body:
            continue
        body.add(bid)
        block = blocks_map.get(bid)
        if block is None:
            continue
        for pred_id in _predecessors_of(bid, blocks_map):
            if pred_id not in body:
                worklist.append(pred_id)
    return body


def _predecessors_of(
    block_id: MIRBlockId,
    blocks_map: dict[MIRBlockId, MIRBlock],
) -> list[MIRBlockId]:
    preds: list[MIRBlockId] = []
    for bid, block in blocks_map.items():
        for succ in _successors(block.terminator):
            if succ == block_id:
                preds.append(bid)
    return preds


def _find_preheader(
    header_id: MIRBlockId,
    body: set[MIRBlockId],
    blocks_map: dict[MIRBlockId, MIRBlock],
    function: MIRFunction,
) -> MIRBlockId | None:
    """Find the preheader: a predecessor of header that is not in the loop body."""
    for pred_id in _predecessors_of(header_id, blocks_map):
        if pred_id not in body:
            return pred_id
    return None


def _def(inst: MIRInstruction) -> int | None:
    if not inst.operands:
        return None
    dest = inst.operands[0]
    if not isinstance(dest, int):
        return None
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV" | "MOVE":
            return dest
        case "MAKE_FUNCTION" | "MAKE_MACRO" | "BUILD_TUPLE" | "CALL" | "APPLY":
            return dest
        case _:
            return None


def _uses(inst: MIRInstruction) -> set[int]:
    result: set[int] = set()
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV":
            pass
        case "MOVE":
            if isinstance(inst.operands[1], int):
                result.add(inst.operands[1])
        case "MAKE_FUNCTION" | "MAKE_MACRO":
            pass
        case "CALL":
            _, op_reg, arg_regs = inst.operands
            if isinstance(op_reg, int):
                result.add(op_reg)
            if isinstance(arg_regs, tuple):
                for r in arg_regs:
                    if isinstance(r, int):
                        result.add(r)
        case "APPLY":
            for op in inst.operands[1:]:
                if isinstance(op, int):
                    result.add(op)
        case "DEFINE_ONCE" | "STORE_LOCAL":
            if isinstance(inst.operands[1], int):
                result.add(inst.operands[1])
        case "BUILD_TUPLE":
            for op in inst.operands[1:]:
                if isinstance(op, int):
                    result.add(op)
        case "APPEND_RESULT":
            if isinstance(inst.operands[0], int):
                result.add(inst.operands[0])
        case _:
            for op in inst.operands:
                if isinstance(op, int):
                    result.add(op)
    return result
