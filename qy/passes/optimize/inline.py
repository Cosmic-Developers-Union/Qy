# coding: utf-8
"""optimize.inline pass。.

把「只被创建一次、体积小、无副作用」的函数内联到唯一的调用点。

健全性判定与实际改写都在 `qy.passes.optimize.inline_core`（与
`optimize.aggressive_inline` 共用同一事实源）；本 pass 只负责策略：
调用点恰好 1 个、块数不超过 ``_MAX_BLOCKS``、非递归、可安全内联。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram
from qy.passes.optimize.facts import rebuild_program
from qy.passes.optimize.inline_core import count_calls
from qy.passes.optimize.inline_core import drop_functions
from qy.passes.optimize.inline_core import find_call_site
from qy.passes.optimize.inline_core import inline_into
from qy.passes.optimize.inline_core import is_inlinable
from qy.passes.optimize.inline_core import is_recursive
from qy.passes.optimize.inline_core import lexical_names
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["InlinePass"]

_MAX_BLOCKS = 3


class InlinePass(Pass):
    def __init__(self):
        super().__init__("optimize.inline")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        result = _inline_program(program)
        return PassResult(success=True, artifact=result)


def _inline_program(program: MIRProgram) -> MIRProgram:
    functions = list(program.functions)
    call_counts = count_calls(functions)
    lexical = lexical_names(program)
    candidates = _find_candidates(functions, call_counts, lexical)

    if not candidates:
        return program

    inlined_indices: set[int] = set()

    for fn_idx in candidates:
        callee = functions[fn_idx]
        site = find_call_site(functions, fn_idx)
        if site is None:
            continue

        caller_idx, block_idx, inst_idx = site
        new_caller = inline_into(functions[caller_idx], block_idx, inst_idx, callee, fn_idx)
        if new_caller is not None:
            functions[caller_idx] = new_caller
            inlined_indices.add(fn_idx)

    if not inlined_indices:
        return program

    new_functions, new_main = drop_functions(functions, inlined_indices, program.main)

    return replace(
        rebuild_program(program, functions=tuple(new_functions), constants=program.constants),
        main=new_main,
    )


def _find_candidates(
    functions: list[MIRFunction],
    call_counts: dict[int, int],
    lexical: frozenset[str],
) -> list[int]:
    candidates: list[int] = []
    for fn_idx, fn in enumerate(functions):
        if call_counts.get(fn_idx, 0) != 1:
            continue
        if len(fn.blocks) > _MAX_BLOCKS:
            continue
        if is_recursive(fn, fn_idx):
            continue
        if not is_inlinable(fn, lexical):
            continue
        candidates.append(fn_idx)
    return candidates
