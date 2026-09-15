# coding: utf-8
"""lir.lower pass — MIR → LIR lowering。.

将 MIR 降到 LIR abstract machine IR，含 instruction selection、layout、ABI、
virtual stack、continuation frame、peephole。

支持两个 dialect：

- ``compat``（默认）：语言级 effect 保留为 ``HANDLE`` / ``PERFORM`` / ``RESUME``
  opcode，可直接被 register VM 编码执行。
- ``abstract-machine``：语言级 effect 被降成 ``HANDLER_PUSH/POP``、``CONT_*``、
  ``EFFECT_UNWIND/DISPATCH``，并填充 handler / continuation / frame layout，
  供 LIR verifier 与后续 backend 消费。当前 Python VM 尚不执行该 dialect，
  因此它用于验证与后续 lowering，而不是默认执行路径。
"""

from __future__ import annotations

from qy.ir.lir import LIRContinuationLayout
from qy.ir.lir import LIRFrameLayout
from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRProgram
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.ir.mir import verify_mir
from qy.passes.lir.compact import compact_registers
from qy.passes.lir.compat_effects import lower_compat_effects
from qy.passes.lir.effects import lower_effects
from qy.passes.lir.linearize import linearize_function
from qy.passes.lir.peephole import peephole
from qy.passes.lir.spaces import assign_symbol_spaces

__all__ = ["_peephole", "lower_lir"]


def lower_lir(program: MIRProgram, *, dialect: str = "compat") -> LIRProgram:
    verifier_diagnostics = verify_mir(program)
    diagnostics = (*program.diagnostics, *verifier_diagnostics)
    if any(d.severity == "error" for d in diagnostics):
        return LIRProgram((), 0, diagnostics)
    resolved_dialect = "abstract-machine" if dialect == "abstract-machine" else "compat"
    return LIRProgram(
        tuple(
            _lower_function(f, program.constants, dialect=resolved_dialect)
            for f in program.functions
        ),
        program.main,
        diagnostics,
        dialect=resolved_dialect,
    )


def _lower_function(
    function: MIRFunction, constants: MIRConstantPool, *, dialect: str = "compat"
) -> LIRFunction:
    instructions = linearize_function(function, constants)
    if dialect == "abstract-machine":
        return _lower_function_abstract_machine(function, instructions)
    instructions = lower_compat_effects(instructions)
    instructions = peephole(instructions)
    instructions, register_count = compact_registers(
        function.params,
        instructions,
        function.register_count,
    )
    return LIRFunction(
        function.name,
        function.params,
        register_count,
        tuple(instructions),
    )


def _lower_function_abstract_machine(function: MIRFunction, instructions: list) -> LIRFunction:
    """Lower effect placeholders to abstract-machine ops and attach layouts.

    ``peephole`` / ``compact_registers`` are intentionally *not* run here:
    both may renumber or remove instructions, which would invalidate the
    absolute instruction indices already patched into ``HANDLER_PUSH``
    targets, ``CONT_CAPTURE`` resume targets and jumps by ``lower_effects``.
    """
    result = lower_effects(_normalize_loads(instructions), function.register_count)
    space_result = assign_symbol_spaces(result.instructions, function_name=function.name.name)
    register_count = result.register_count
    frame_layout = LIRFrameLayout(
        kind="function",
        name=function.name.name,
        register_count=register_count,
        # Conservative: every register is treated as frame-resident until a
        # liveness-based slot assignment lands. L5 then verifies the bounds.
        saved_registers=tuple(range(register_count)),
    )
    continuations = tuple(
        LIRContinuationLayout(
            id=continuation.id,
            resume_target=continuation.resume_target,
            # Conservative saved set; liveness refinement is future work.
            saved_registers=tuple(range(register_count)),
            saved_spaces=continuation.saved_spaces,
            multi_shot=continuation.multi_shot,
        )
        for continuation in result.continuations
    )
    return LIRFunction(
        function.name,
        function.params,
        register_count,
        tuple(space_result.instructions),
        frame_layout=frame_layout,
        symbol_spaces=space_result.symbol_spaces,
        continuations=continuations,
        handlers=result.handlers,
    )


_peephole = peephole


def _normalize_loads(instructions: list) -> list:
    """In-place ``LOAD_HOST nil/T`` -> ``LOAD_NIL``/``LOAD_T`` rewrite.

    The compat path gets this from ``peephole``; the abstract-machine path
    must not run ``peephole`` (it can change instruction count), so the
    count-preserving subset is applied directly.
    """
    from qy.ir.lir import LIRInstruction
    from qy.sem.core import T as QY_T

    out = []
    for inst in instructions:
        if inst.opcode == "LOAD_HOST" and len(inst.operands) >= 2:
            dest, value = inst.operands[0], inst.operands[1]
            if value is None:
                out.append(LIRInstruction("LOAD_NIL", (dest,), inst.span))
                continue
            if value is QY_T:
                out.append(LIRInstruction("LOAD_T", (dest,), inst.span))
                continue
        out.append(inst)
    return out
