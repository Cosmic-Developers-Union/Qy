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
from qy.passes.optimize.facts import rebuild_function
from qy.passes.optimize.facts import rebuild_program
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
        seen: dict[object, int] = {}  # intern key -> new index

        for old_idx, value in enumerate(program.constants.values):
            key = _intern_key(value)
            existing = None if key is None else seen.get(key)
            if existing is not None:
                old_to_new[old_idx] = existing
            else:
                new_idx = new_pool.intern(value)
                if key is not None:
                    seen[key] = new_idx
                old_to_new[old_idx] = new_idx

        # Remap all constant references in functions
        new_functions = tuple(_remap_constants(f, old_to_new) for f in program.functions)

        return PassResult(
            success=True,
            artifact=rebuild_program(program, functions=new_functions, constants=new_pool),
        )


def _remap_constants(function: MIRFunction, old_to_new: dict[int, int]) -> MIRFunction:
    """把函数内 ``LOAD_CONST`` 的常量下标按 old_to_new 重写。."""
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

    return rebuild_function(function, blocks=tuple(new_blocks))


_SAFE_INTERN_BASES: tuple[type, ...] = ()


def _safe_intern_bases() -> tuple[type, ...]:
    """可以安全去重的常量类型（惰性初始化，避免与 sem 的 import 顺序耦合）。."""
    global _SAFE_INTERN_BASES
    if not _SAFE_INTERN_BASES:
        from qy.core.syntax import NONE
        from qy.core.syntax import T
        from qy.core.syntax import nil
        from qy.sem.core import NumberValue

        _SAFE_INTERN_BASES = (NumberValue, type(T), type(nil), type(NONE))
    return _SAFE_INTERN_BASES


def _intern_key(value: object) -> object | None:
    """常量去重键；返回 ``None`` 表示「不得去重，必须保留独立实例」。.

    - 只用 ``hash(value)`` 会把不同值合并：``T`` 与 ``none`` 都是空 frozen
      dataclass，``hash`` 相同但语义不同；
    - 只对 identity **不可观察**的类型去重：数值（按值比较）与 Qy 自身对象单例。
      字符串 / 字符 / symbol / chain 的 identity 目前是可观察的（``=`` 对它们按
      identity 比较，例如 ``(= "abc" "abc")`` 为 ``nil``），合并实例会改变语义。
    """
    if not isinstance(value, _safe_intern_bases()):
        return None
    try:
        hash(value)
    except TypeError:
        return None
    return (type(value), value)
