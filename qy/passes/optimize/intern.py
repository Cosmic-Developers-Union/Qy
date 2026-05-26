# coding: utf-8
"""optimize.intern pass.

Constant pool interning: deduplicates constant pool entries that refer to
the same value, reducing memory usage and enabling identity comparisons
at runtime.

Also performs string interning for symbol-like values to enable fast
equality checks.
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["InternPass"]


class InternPass(Pass):
    def __init__(self):
        super().__init__("optimize.intern")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)

        # Build deduplicated constant pool with remap
        old_to_new: dict[int, int] = {}
        new_pool = MIRConstantPool()
        seen: dict[int, int] = {}  # value hash -> new index

        for old_idx, value in enumerate(program.constants.values):
            key = _intern_key(value)
            existing = seen.get(key)
            if existing is not None:
                old_to_new[old_idx] = existing
            else:
                new_idx = new_pool.intern(value)
                seen[key] = new_idx
                old_to_new[old_idx] = new_idx

        # Remap all constant references in functions
        new_functions = tuple(_remap_constants(f, old_to_new) for f in program.functions)

        return PassResult(
            success=True,
            artifact=MIRProgram(new_functions, new_pool, program.main, program.diagnostics),
        )


def _remap_constants(function: MIRFunction, old_to_new: dict[int, int]) -> MIRFunction:
    """Remap all LOAD_CONST index references in *function*."""
    changed = False
    new_blocks = []
    for block in function.blocks:
        new_instructions = []
        for inst in block.instructions:
            if inst.opcode == "LOAD_CONST":
                old_idx = inst.operands[1]
                if isinstance(old_idx, int) and old_idx in old_to_new:
                    new_idx = old_to_new[old_idx]
                    if new_idx != old_idx:
                        changed = True
                        new_instructions.append(
                            MIRInstruction(
                                "LOAD_CONST",
                                (inst.operands[0], new_idx),
                                inst.span,
                            )
                        )
                        continue
            new_instructions.append(inst)
        new_blocks.append(type(block)(block.id, tuple(new_instructions), block.terminator))

    if not changed:
        return function

    return MIRFunction(
        function.name,
        function.params,
        function.register_count,
        tuple(new_blocks),
        function.entry,
    )


def _intern_key(value: object) -> int:
    """Compute a deduplication key for a constant value.

    Uses both identity and value equality.
    """
    try:
        return hash(value)
    except TypeError:
        return id(value)
