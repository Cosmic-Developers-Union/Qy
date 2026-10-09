# coding: utf-8
"""optimize.aggressive_inline pass.

比 `optimize.inline` 更激进的内联策略：

- 多调用点内联（不限于恰好一次创建）；
- 指令预算（``max_instructions``）而非固定块数；
- 迭代到 ``max_depth`` 轮，允许跨层展开。

健全性判定与实际改写都在 `qy.passes.optimize.inline_core`（同一事实源）：
闭包变量、形参替换、effect / 空间副作用、寄存器位移都由内核负责，本 pass 只做策略。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.passes.optimize.facts import rebuild_program
from qy.passes.optimize.inline_core import count_calls
from qy.passes.optimize.inline_core import drop_functions
from qy.passes.optimize.inline_core import find_all_call_sites
from qy.passes.optimize.inline_core import inline_into
from qy.passes.optimize.inline_core import is_inlinable
from qy.passes.optimize.inline_core import is_recursive
from qy.passes.optimize.inline_core import lexical_names
from qy.passes.optimize.inline_core import referenced_fn_indices
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["AggressiveInlinePass"]

_MAX_INLINED_INSTRUCTIONS = 64
_MAX_INLINE_DEPTH = 4


class AggressiveInlinePass(Pass):
    def __init__(
        self,
        max_instructions: int = _MAX_INLINED_INSTRUCTIONS,
        max_depth: int = _MAX_INLINE_DEPTH,
    ):
        super().__init__("optimize.aggressive_inline")
        self.max_instructions = max_instructions
        self.max_depth = max_depth

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        result = _aggressive_inline(program, self.max_instructions, self.max_depth)
        return PassResult(success=True, artifact=result)


def _aggressive_inline(
    program: MIRProgram,
    max_instructions: int,
    max_depth: int,
) -> MIRProgram:
    """迭代内联小函数，直到没有候选或用完深度。."""
    functions = list(program.functions)
    main = program.main
    lexical = lexical_names(program)

    for _depth in range(max_depth):
        call_counts = count_calls(functions)
        candidates = _find_candidates(functions, call_counts, lexical, max_instructions)
        if not candidates:
            break

        inlined_any = False
        inlined_indices: set[int] = set()

        for fn_idx in candidates:
            callee = functions[fn_idx]
            for caller_idx, block_idx, inst_idx in find_all_call_sites(functions, fn_idx):
                new_caller = inline_into(functions[caller_idx], block_idx, inst_idx, callee, fn_idx)
                if new_caller is not None:
                    functions[caller_idx] = new_caller
                    inlined_indices.add(fn_idx)
                    inlined_any = True
                    break  # 修改后重新分析

        if not inlined_any:
            break

        if inlined_indices:
            droppable = inlined_indices - referenced_fn_indices(functions)
            if droppable:
                functions, main = drop_functions(functions, droppable, main)

    return replace(
        rebuild_program(program, functions=tuple(functions), constants=program.constants),
        main=main,
    )


def _find_candidates(
    functions: list[MIRFunction],
    call_counts: dict[int, int],
    lexical: frozenset[str],
    max_instructions: int,
) -> list[int]:
    candidates: list[int] = []
    for fn_idx, fn in enumerate(functions):
        if call_counts.get(fn_idx, 0) == 0:
            continue
        if sum(len(block.instructions) for block in fn.blocks) > max_instructions:
            continue
        if is_recursive(fn, fn_idx):
            continue
        if not is_inlinable(fn, lexical):
            continue
        candidates.append(fn_idx)
    return candidates
