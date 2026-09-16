# coding: utf-8
"""MIR liveness analysis.

Computes per-block live-in / live-out sets and per-register live intervals.
Used by register allocation, DCE, dead store elimination, and loop-invariant
code motion.
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.ir.mir import MIRBlockId
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRTerminator
from qy.ir.mir import terminator_targets

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
            # terminator 的寄存器使用是块末尾的使用，必须进入 live_out；
            # 否则只在 terminator 中被读取的寄存器（TAIL_CALL 参数、RETURN 值、
            # BRANCH 条件等）活跃区间会提前结束，寄存器分配误复用（历史缺陷）。
            new_out: set[int] = set(_terminator_uses(block.terminator))
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
    """CFG 后继；直接复用 `qy.ir.mir` 的 terminator 目标语义。.

    必须包含 ``EFFECT_PERFORM`` 的 resume 边：否则 resume 之后的寄存器使用不会
    进入活跃区间，寄存器分配会过早复用（历史缺陷）。
    """
    return terminator_targets(term)


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

        for used in _terminator_uses(block.terminator):
            if used not in k:
                g.add(used)
        term_dest = _terminator_def(block.terminator)
        if term_dest is not None:
            k.add(term_dest)

        gen[block.id] = frozenset(g)
        kill[block.id] = frozenset(k)

    return gen, kill


def _terminator_uses(term: MIRTerminator) -> set[int]:
    """Terminator 读取的寄存器集合（MIR 寄存器表减去 def 位置）。."""
    from qy.ir.mir import terminator_register_def_position
    from qy.ir.mir import terminator_register_positions

    result: set[int] = set()
    def_position = terminator_register_def_position(term)
    operands = term.operands
    for index in terminator_register_positions(term):
        if index == def_position or index >= len(operands):
            continue
        value = operands[index]
        if isinstance(value, tuple):
            for item in value:
                _add_int(item, result)
        else:
            _add_int(value, result)
    # TAIL_CALL 的参数列表在位置 1
    if term.opcode == "TAIL_CALL" and len(operands) >= 2 and isinstance(operands[1], tuple):
        for item in operands[1]:
            _add_int(item, result)
    return result


def _uses(inst: MIRInstruction) -> set[int]:
    """指令读取的寄存器集合（MIR 寄存器操作数表减去 def 位置）。."""
    from qy.ir.mir import register_def_position
    from qy.ir.mir import register_operand_positions
    from qy.ir.mir import register_tuple_positions

    result: set[int] = set()
    def_position = register_def_position(inst)
    operands = inst.operands
    for index in register_operand_positions(inst):
        if index == def_position:
            continue
        if index < len(operands):
            _add_int(operands[index], result)
    for index in register_tuple_positions(inst):
        if index == def_position or index >= len(operands):
            continue
        value = operands[index]
        if isinstance(value, tuple):
            for item in value:
                _add_int(item, result)
    return result


def _def(inst: MIRInstruction) -> int | None:
    """指令写入的寄存器（MIR 寄存器 def 位置）。."""
    from qy.ir.mir import register_def_position

    position = register_def_position(inst)
    if position is None or position >= len(inst.operands):
        return None
    dest = inst.operands[position]
    return dest if isinstance(dest, int) else None


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
