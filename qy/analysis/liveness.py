# coding: utf-8
"""MIR liveness analysis.

Computes per-block live-in / live-out sets and per-register live intervals.
Used by register allocation, DCE, dead store elimination, and loop-invariant
code motion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.ir.mir import MIRBlockId
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRTerminator

__all__ = [
    "LiveIntervals",
    "LivenessInfo",
    "compute_liveness",
    "live_in",
    "live_out",
]


@dataclass(frozen=True, slots=True)
class LiveIntervals:
    """Per-register first-def and last-use positions (flat instruction index)."""

    intervals: dict[int, tuple[int, int]]  # reg -> (first_def, last_use)


@dataclass(frozen=True, slots=True)
class LivenessInfo:
    """Complete liveness information for one MIR function."""

    live_in: dict[MIRBlockId, frozenset[int]]
    live_out: dict[MIRBlockId, frozenset[int]]
    gen: dict[MIRBlockId, frozenset[int]]
    kill: dict[MIRBlockId, frozenset[int]]
    intervals: LiveIntervals


def compute_liveness(function: MIRFunction) -> LivenessInfo:
    """Compute live-in, live-out, and intervals for *function*."""
    {b.id: b for b in function.blocks}
    successors_map = _compute_successors(function)

    gen, kill = _compute_gen_kill(function)

    live_in = {b.id: frozenset() for b in function.blocks}
    live_out = {b.id: frozenset() for b in function.blocks}

    changed = True
    while changed:
        changed = False
        for block in function.blocks:
            new_out: set[int] = set()
            for succ_id in successors_map.get(block.id, ()):
                new_out |= live_in.get(succ_id, frozenset())

            new_in = gen[block.id] | (frozenset(new_out) - kill[block.id])

            if new_in != live_in[block.id] or frozenset(new_out) != live_out[block.id]:
                changed = True
                live_in[block.id] = new_in
                live_out[block.id] = frozenset(new_out)

    intervals = _compute_intervals(function, live_in, live_out)

    return LivenessInfo(
        live_in=live_in,
        live_out=live_out,
        gen=gen,
        kill=kill,
        intervals=intervals,
    )


def live_in(info: LivenessInfo, block_id: MIRBlockId) -> frozenset[int]:
    return info.live_in.get(block_id, frozenset())


def live_out(info: LivenessInfo, block_id: MIRBlockId) -> frozenset[int]:
    return info.live_out.get(block_id, frozenset())


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _compute_successors(function: MIRFunction) -> dict[MIRBlockId, list[MIRBlockId]]:
    result: dict[MIRBlockId, list[MIRBlockId]] = {}
    for block in function.blocks:
        result[block.id] = _terminator_successors(block.terminator)
    return result


def _terminator_successors(term: MIRTerminator) -> list[MIRBlockId]:
    match term.opcode:
        case "JUMP":
            return [cast(int, term.operands[0])]
        case "BRANCH":
            _, true_b, false_b = term.operands
            return [cast(int, true_b), cast(int, false_b)]
        case _:
            return []


def _compute_gen_kill(
    function: MIRFunction,
) -> tuple[dict[MIRBlockId, frozenset[int]], dict[MIRBlockId, frozenset[int]]]:
    gen: dict[MIRBlockId, frozenset[int]] = {}
    kill: dict[MIRBlockId, frozenset[int]] = {}

    for block in function.blocks:
        g: set[int] = set()
        k: set[int] = set()

        for inst in block.instructions:
            for used in _uses(inst):
                if used not in k:
                    g.add(used)
            dest = _def(inst)
            if dest is not None:
                k.add(dest)

        term_dest = _terminator_def(block.terminator)
        if term_dest is not None:
            k.add(term_dest)

        gen[block.id] = frozenset(g)
        kill[block.id] = frozenset(k)

    return gen, kill


def _uses(inst: MIRInstruction) -> set[int]:
    """Return registers read by *inst* (not counting the dest)."""
    result: set[int] = set()
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV":
            pass
        case "MOVE":
            _add_int(inst.operands[1], result)
        case "MAKE_FUNCTION" | "MAKE_MACRO":
            pass
        case "CALL":
            _, op_reg, arg_regs = inst.operands
            _add_int(op_reg, result)
            if isinstance(arg_regs, tuple):
                for r in arg_regs:
                    _add_int(r, result)
        case "APPLY":
            for op in inst.operands[1:]:
                _add_int(op, result)
        case "DEFINE_ONCE" | "STORE_LOCAL":
            _add_int(inst.operands[1], result)
        case "BUILD_TUPLE":
            for op in inst.operands[1:]:
                _add_int(op, result)
        case "APPEND_RESULT":
            _add_int(inst.operands[0], result)
        case "EFFECT_RESUME":
            for op in inst.operands[1:]:
                _add_int(op, result)
        case "RUNTIME_EVAL":
            for op in inst.operands[1:]:
                _add_int(op, result)
        case _:
            for op in inst.operands:
                if isinstance(op, int):
                    result.add(op)
    return result


def _def(inst: MIRInstruction) -> int | None:
    """Return the register defined by *inst*, if any."""
    if not inst.operands:
        return None
    dest = inst.operands[0]
    if inst.opcode in (
        "LOAD_CONST",
        "LOAD_HOST",
        "LOAD_ENV",
        "MOVE",
        "MAKE_FUNCTION",
        "MAKE_MACRO",
        "BUILD_TUPLE",
        "CALL",
        "APPLY",
    ):
        if isinstance(dest, int):
            return dest
    if inst.opcode in ("DEFINE_ONCE", "STORE_LOCAL"):
        return None
    if inst.opcode == "APPEND_RESULT":
        return None
    return None


def _terminator_def(term: MIRTerminator) -> int | None:
    if term.opcode == "EFFECT_PERFORM" and len(term.operands) >= 1:
        dest = term.operands[0]
        if isinstance(dest, int):
            return dest
    return None


def _add_int(value: object, target: set[int]) -> None:
    if isinstance(value, int):
        target.add(value)


def _compute_intervals(
    function: MIRFunction,
    live_in: dict[MIRBlockId, frozenset[int]],
    live_out: dict[MIRBlockId, frozenset[int]],
) -> LiveIntervals:
    """Compute flat (first_def, last_use) intervals for each register.

    Uses a simple linear scan of blocks in program order.
    """
    first_def: dict[int, int] = {}
    last_use: dict[int, int] = {}

    flat_idx = 0
    for block in function.blocks:
        for reg in live_in.get(block.id, frozenset()):
            if reg not in first_def:
                first_def[reg] = flat_idx

        for inst in block.instructions:
            dest = _def(inst)
            if dest is not None and dest not in first_def:
                first_def[dest] = flat_idx

            for used in _uses(inst):
                last_use[used] = flat_idx

            flat_idx += 1

        for reg in live_out.get(block.id, frozenset()):
            last_use[reg] = flat_idx

        flat_idx += 1  # account for terminator

    intervals: dict[int, tuple[int, int]] = {}
    for reg in set(first_def) | set(last_use):
        d = first_def.get(reg, 0)
        u = last_use.get(reg, d)
        intervals[reg] = (d, u)

    return LiveIntervals(intervals=intervals)
