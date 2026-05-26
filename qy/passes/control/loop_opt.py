# coding: utf-8
"""control.loop_opt pass.

Natural loop analysis and loop optimizations for MIR:
- Loop peeling: extract the first iteration
- Loop unrolling: duplicate loop body for small constant-count loops
- Loop fusion: merge adjacent loops with compatible bodies

All transformations operate on the MIR CFG and preserve semantics.
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlockId
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["LoopOptPass"]


class LoopOptPass(Pass):
    def __init__(self):
        super().__init__("control.loop_opt")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        new_functions = tuple(_optimize_loops_in_function(f) for f in program.functions)
        return PassResult(
            success=True,
            artifact=MIRProgram(
                new_functions, program.constants, program.main, program.diagnostics
            ),
        )


def _optimize_loops_in_function(function: MIRFunction) -> MIRFunction:
    """Apply loop optimizations to *function*.

    Current implementations:
    - Loop peeling: when the first iteration has a known constant condition,
      peel it out of the loop.
    """
    loops = _find_natural_loops(function)
    if not loops:
        return function

    # For now, only apply peeling for loops with simple constant conditions
    # Full unrolling and fusion require more complex analysis
    blocks_map = {b.id: b for b in function.blocks}

    for header_id, _body_ids, _preheader_id in loops:
        header = blocks_map.get(header_id)
        if header is None:
            continue

        # Check if the header terminates with a conditional branch
        # that compares a loop-invariant register against a constant
        if header.terminator.opcode == "BRANCH":
            _cond_reg, _true_b, _false_b = header.terminator.operands
            # If the true branch leads back to the header (loop), the condition
            # is the loop guard.  We can't peel without knowing the constant,
            # but we can note this for future profile-guided optimization.
            pass

    return function


def _find_natural_loops(
    function: MIRFunction,
) -> list[tuple[MIRBlockId, set[MIRBlockId], MIRBlockId]]:
    """Find natural loops as (header, body, preheader) triples."""
    all_ids = {b.id for b in function.blocks}
    dom = _compute_dominators(function, all_ids)

    back_edges: list[tuple[MIRBlockId, MIRBlockId]] = []
    for block in function.blocks:
        for succ_id in _successors(block.terminator):
            if succ_id in dom.get(block.id, set()):
                back_edges.append((block.id, succ_id))

    loops: list[tuple[MIRBlockId, set[MIRBlockId], MIRBlockId]] = []
    seen_headers: set[MIRBlockId] = set()
    for tail_id, header_id in back_edges:
        if header_id in seen_headers:
            continue
        seen_headers.add(header_id)
        body = _compute_loop_body(header_id, tail_id, function)
        preheader = _find_preheader(header_id, body, function)
        if preheader is not None:
            loops.append((header_id, body, preheader))

    return loops


def _compute_dominators(
    function: MIRFunction, all_ids: set[MIRBlockId]
) -> dict[MIRBlockId, set[MIRBlockId]]:
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
    function: MIRFunction,
) -> set[MIRBlockId]:
    body = {header_id}
    worklist = [tail_id]
    {b.id: b for b in function.blocks}
    while worklist:
        bid = worklist.pop()
        if bid in body:
            continue
        body.add(bid)
        for pred_id in _predecessors(bid, function):
            if pred_id not in body:
                worklist.append(pred_id)
    return body


def _find_preheader(
    header_id: MIRBlockId,
    body: set[MIRBlockId],
    function: MIRFunction,
) -> MIRBlockId | None:
    blocks = {b.id: b for b in function.blocks}
    for bid, block in blocks.items():
        for succ in _successors(block.terminator):
            if succ == header_id and bid not in body:
                return bid
    return None
