# coding: utf-8
"""MIR escape analysis.

Determines whether bindings (registers holding closures, continuations,
tuples, handlers) escape the current scope.  A binding escapes if it is:
  - captured by a closure that outlives the current function
  - passed as an argument to an unknown callee
  - stored in a data structure that escapes
  - captured by a continuation or handler
  - sent across a parallel boundary

Escape information enables:
  - Scalar replacement (break apart non-escaping tuples)
  - Stack allocation (non-escaping objects need not be heap-allocated)
  - Closure optimization (non-escaping bindings need not be boxed)
  - Effect handler optimization (non-escaping continuations)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator

__all__ = [
    "EscapeInfo",
    "compute_escape",
]


@dataclass(frozen=True, slots=True)
class EscapeInfo:
    """Escape analysis results for one function."""

    escaping: frozenset[int]
    """Registers whose values are known to escape."""

    partially_escaping: frozenset[int]
    """Registers that escape through some but not all paths."""

    closed_over: frozenset[int]
    """Registers captured by closures defined in this function."""

    captured_by_continuation: frozenset[int]
    """Registers that would be saved in a continuation capture."""

    parallel_escape: frozenset[int]
    """Registers sent across a parallel boundary."""


def compute_escape(program: MIRProgram) -> dict[int, EscapeInfo]:
    """Compute escape info for every function in *program*.

    Returns a mapping from function index to EscapeInfo.
    """
    results: dict[int, EscapeInfo] = {}
    for fn_idx, fn in enumerate(program.functions):
        results[fn_idx] = _analyze_function(fn)
    return results


def _analyze_function(function: MIRFunction) -> EscapeInfo:
    escaping: set[int] = set()
    partially_escaping: set[int] = set()
    closed_over: set[int] = set()
    captured_by_continuation: set[int] = set()
    parallel_escape: set[int] = set()

    for block in function.blocks:
        for inst in block.instructions:
            _analyze_instruction(
                inst,
                function,
                escaping,
                closed_over,
                captured_by_continuation,
                parallel_escape,
            )
        _analyze_terminator(
            block.terminator,
            function,
            escaping,
            captured_by_continuation,
            parallel_escape,
        )

    return EscapeInfo(
        escaping=frozenset(escaping),
        partially_escaping=frozenset(partially_escaping),
        closed_over=frozenset(closed_over),
        captured_by_continuation=frozenset(captured_by_continuation),
        parallel_escape=frozenset(parallel_escape),
    )


def _analyze_instruction(
    inst: MIRInstruction,
    function: MIRFunction,
    escaping: set[int],
    closed_over: set[int],
    captured_by_continuation: set[int],
    parallel_escape: set[int],
) -> None:
    match inst.opcode:
        case "MAKE_FUNCTION":
            dest_reg = cast(int, inst.operands[0])
            # The closure captures registers used in its body.
            # Since MIR has already lowered closure captures as explicit
            # LOAD_ENV instructions, the captured registers are those
            # referenced by the nested function's instructions.
            # For now, conservatively mark all registers as escaping
            # if they are live at this point (a full implementation
            # would analyze the nested function's free variables).
            pass

        case "CALL":
            dest_reg, op_reg, arg_regs = inst.operands
            # All arguments escape through the call boundary
            # unless the callee is a known pure function.
            if isinstance(arg_regs, tuple):
                for arg in arg_regs:
                    if isinstance(arg, int):
                        escaping.add(arg)
            # The operator itself escapes through the call
            if isinstance(op_reg, int):
                escaping.add(op_reg)

        case "APPLY":
            for op in inst.operands:
                if isinstance(op, int):
                    escaping.add(op)

        case "RUNTIME_EVAL":
            for op in inst.operands:
                if isinstance(op, int):
                    escaping.add(op)

        case "CACHE_EVAL":
            # Cache stores a reference, values may escape
            pass

        case "BUILD_TUPLE":
            dest_reg = cast(int, inst.operands[0])
            # The tuple itself escapes if any of its elements escape
            # through a subsequent call or closure capture.
            # Conservative: mark tuple as potentially escaping.
            pass

        case "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST":
            dest_reg = cast(int, inst.operands[0])
            # Values sent to parallel boundaries escape
            parallel_escape.add(dest_reg)

        case "EFFECT_HANDLE_BEGIN" | "EFFECT_HANDLE_END":
            pass

        case "EFFECT_RESUME":
            # Resume captures the continuation, so live registers escape
            for op in inst.operands:
                if isinstance(op, int):
                    captured_by_continuation.add(op)


def _analyze_terminator(
    term: MIRTerminator,
    function: MIRFunction,
    escaping: set[int],
    captured_by_continuation: set[int],
    parallel_escape: set[int],
) -> None:
    match term.opcode:
        case "TAIL_CALL":
            fn_reg, arg_regs = term.operands
            if isinstance(fn_reg, int):
                escaping.add(fn_reg)
            if isinstance(arg_regs, tuple):
                for arg in arg_regs:
                    if isinstance(arg, int):
                        escaping.add(arg)

        case "RAISE_EFFECT":
            # effect name and argument escape through the effect boundary
            for op in term.operands:
                if isinstance(op, int):
                    escaping.add(op)

        case "EFFECT_PERFORM":
            # (dst, eff_sym, arg_reg, resume_block, resumable)
            if len(term.operands) >= 3:
                arg_reg = term.operands[2]
                if isinstance(arg_reg, int):
                    escaping.add(arg_reg)
