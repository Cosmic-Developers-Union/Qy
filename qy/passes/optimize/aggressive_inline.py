# coding: utf-8
"""optimize.aggressive_inline pass.

Aggressive inlining: extends basic InlinePass with:
- Multi-call-site inlining (not limited to single call sites)
- Cross-function inlining (inline through intermediate wrappers)
- Configurable size threshold instead of fixed block limit
- Inlining through effect-free call chains (A calls B calls C)

Conservative guards:
- Maximum total inlined instruction count per function
- Maximum inlining depth to prevent infinite expansion
- No inlining of recursive functions
- No inlining across effect boundaries
"""

from __future__ import annotations

from typing import cast

from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["AggressiveInlinePass"]

_MAX_INLINED_INSTRUCTIONS = 64
_MAX_INLINE_DEPTH = 4
_EFFECT_OPCODES = frozenset(
    {
        "HANDLE",
        "PERFORM",
        "RESUME",
        "RAISE_EFFECT",
        "EFFECT_HANDLE_BEGIN",
        "EFFECT_HANDLE_END",
        "EFFECT_RESUME",
    }
)


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
    """Iteratively inline small functions until no more candidates remain."""
    functions = list(program.functions)
    main = program.main

    for _depth in range(max_depth):
        call_counts = _count_calls(functions)
        candidates = _find_candidates(functions, call_counts, max_instructions)
        if not candidates:
            break

        inlined_any = False
        inlined_indices: set[int] = set()

        for fn_idx in candidates:
            callee = functions[fn_idx]
            call_sites = _find_all_call_sites(functions, fn_idx)

            for caller_idx, block_idx, inst_idx in call_sites:
                caller = functions[caller_idx]
                new_caller = _inline_into(
                    caller,
                    block_idx,
                    inst_idx,
                    callee,
                    fn_idx,
                    max_instructions,
                )
                if new_caller is not None:
                    functions[caller_idx] = new_caller
                    inlined_indices.add(fn_idx)
                    inlined_any = True
                    break  # Re-analyze after modification

        if not inlined_any:
            break

        if inlined_indices:
            index_map: dict[int, int] = {}
            new_functions: list[MIRFunction] = []
            for old_idx, fn in enumerate(functions):
                if old_idx in inlined_indices:
                    continue
                index_map[old_idx] = len(new_functions)
                new_functions.append(fn)
            functions = [_remap_fn_indices(f, index_map) for f in new_functions]
            main = index_map.get(program.main, 0)

    return MIRProgram(tuple(functions), program.constants, main, program.diagnostics)


def _count_calls(functions: list[MIRFunction]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for fn in functions:
        for block in fn.blocks:
            for inst in block.instructions:
                if inst.opcode == "MAKE_FUNCTION":
                    fn_idx = inst.operands[1]
                    if isinstance(fn_idx, int):
                        counts[fn_idx] = counts.get(fn_idx, 0) + 1
    return counts


def _find_candidates(
    functions: list[MIRFunction],
    call_counts: dict[int, int],
    max_instructions: int,
) -> list[int]:
    candidates: list[int] = []
    for fn_idx, fn in enumerate(functions):
        if call_counts.get(fn_idx, 0) == 0:
            continue
        total_insts = sum(len(b.instructions) for b in fn.blocks)
        if total_insts > max_instructions:
            continue
        if _has_effects(fn):
            continue
        if _is_recursive(fn, fn_idx):
            continue
        candidates.append(fn_idx)
    return candidates


def _has_effects(fn: MIRFunction) -> bool:
    for block in fn.blocks:
        for inst in block.instructions:
            if inst.opcode in _EFFECT_OPCODES:
                return True
        if block.terminator.opcode in ("RAISE_EFFECT", "EFFECT_PERFORM"):
            return True
        if block.terminator.opcode == "TAIL_CALL":
            return True
    return False


def _is_recursive(fn: MIRFunction, fn_idx: int) -> bool:
    for block in fn.blocks:
        for inst in block.instructions:
            if inst.opcode == "MAKE_FUNCTION" and inst.operands[1] == fn_idx:
                return True
    return False


def _find_all_call_sites(
    functions: list[MIRFunction], target_fn_idx: int
) -> list[tuple[int, int, int]]:
    sites: list[tuple[int, int, int]] = []
    for caller_idx, caller in enumerate(functions):
        make_fn_reg: int | None = None
        defined_symbol: object | None = None

        for bi, block in enumerate(caller.blocks):
            for ii, inst in enumerate(block.instructions):
                if inst.opcode == "MAKE_FUNCTION" and inst.operands[1] == target_fn_idx:
                    make_fn_reg = cast(int, inst.operands[0])

                if (
                    inst.opcode == "DEFINE_ONCE"
                    and make_fn_reg is not None
                    and inst.operands[1] == make_fn_reg
                ):
                    defined_symbol = inst.operands[0]

                if inst.opcode == "LOAD_ENV" and defined_symbol is not None:
                    load_sym = inst.operands[1]
                    if _same_symbol(load_sym, defined_symbol):
                        make_fn_reg = cast(int, inst.operands[0])

                if (
                    inst.opcode == "CALL"
                    and make_fn_reg is not None
                    and inst.operands[1] == make_fn_reg
                ):
                    sites.append((caller_idx, bi, ii))

    return sites


def _same_symbol(a: object, b: object) -> bool:
    from qy.frontend.reader import Symbol

    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    return a == b


def _inline_into(
    caller: MIRFunction,
    call_block_idx: int,
    call_inst_idx: int,
    callee: MIRFunction,
    callee_fn_idx: int,
    max_instructions: int,
) -> MIRFunction | None:
    call_block = caller.blocks[call_block_idx]
    call_inst = call_block.instructions[call_inst_idx]
    dest_reg, _op_reg, arg_regs = call_inst.operands

    if not isinstance(arg_regs, tuple):
        return None
    if len(arg_regs) != len(callee.params):
        return None

    reg_offset = caller.register_count
    max_block_id = max(b.id for b in caller.blocks) + 1

    param_moves: list[MIRInstruction] = []
    for param_idx, arg_reg in enumerate(arg_regs):
        target_reg = param_idx + reg_offset
        if arg_reg != target_reg:
            param_moves.append(MIRInstruction("MOVE", (target_reg, arg_reg), call_inst.span))

    inlined_entry_id = max_block_id + callee.entry
    continuation_id = max_block_id + len(callee.blocks)

    pre_instructions = (*call_block.instructions[:call_inst_idx], *param_moves)
    pre_block = MIRBlock(
        call_block.id,
        tuple(
            i
            for i in pre_instructions
            if i.opcode != "MAKE_FUNCTION" or i.operands[1] != callee_fn_idx
        ),
        MIRTerminator("JUMP", (inlined_entry_id,), call_inst.span),
    )

    post_instructions = call_block.instructions[call_inst_idx + 1 :]
    continuation_block = MIRBlock(continuation_id, post_instructions, call_block.terminator)

    inlined_blocks: list[MIRBlock] = []
    for block in callee.blocks:
        new_id = max_block_id + block.id
        new_instructions = list(
            _offset_instruction(inst, reg_offset) for inst in block.instructions
        )
        if block.terminator.opcode == "RETURN":
            ret_reg = cast(int, block.terminator.operands[0]) + reg_offset
            if ret_reg != dest_reg:
                new_instructions.append(
                    MIRInstruction("MOVE", (dest_reg, ret_reg), block.terminator.span)
                )
            new_terminator = MIRTerminator("JUMP", (continuation_id,), block.terminator.span)
        else:
            new_terminator = _offset_terminator(block.terminator, reg_offset, max_block_id)
        inlined_blocks.append(MIRBlock(new_id, tuple(new_instructions), new_terminator))

    new_blocks = list(caller.blocks)
    new_blocks[call_block_idx] = pre_block
    new_blocks.append(continuation_block)
    new_blocks.extend(inlined_blocks)

    return MIRFunction(
        caller.name,
        caller.params,
        caller.register_count + callee.register_count,
        tuple(new_blocks),
        caller.entry,
    )


def _offset_instruction(inst: MIRInstruction, reg_offset: int) -> MIRInstruction:
    match inst.opcode:
        case "LOAD_CONST" | "LOAD_HOST" | "LOAD_ENV":
            return MIRInstruction(
                inst.opcode,
                (cast(int, inst.operands[0]) + reg_offset, *inst.operands[1:]),
                inst.span,
            )
        case "MOVE":
            return MIRInstruction(
                "MOVE",
                (
                    cast(int, inst.operands[0]) + reg_offset,
                    cast(int, inst.operands[1]) + reg_offset,
                ),
                inst.span,
            )
        case "CALL":
            dest, op, args = inst.operands
            return MIRInstruction(
                "CALL",
                (
                    cast(int, dest) + reg_offset,
                    cast(int, op) + reg_offset,
                    tuple(cast(int, a) + reg_offset for a in cast(tuple, args)),
                ),
                inst.span,
            )
        case "DEFINE_ONCE":
            return MIRInstruction(
                "DEFINE_ONCE",
                (inst.operands[0], cast(int, inst.operands[1]) + reg_offset),
                inst.span,
            )
        case "STORE_LOCAL":
            return MIRInstruction(
                "STORE_LOCAL",
                (inst.operands[0], cast(int, inst.operands[1]) + reg_offset),
                inst.span,
            )
        case "APPEND_RESULT":
            return MIRInstruction(
                "APPEND_RESULT", (cast(int, inst.operands[0]) + reg_offset,), inst.span
            )
        case "BUILD_TUPLE":
            return MIRInstruction(
                "BUILD_TUPLE",
                tuple(op + reg_offset if isinstance(op, int) else op for op in inst.operands),
                inst.span,
            )
        case "MAKE_FUNCTION":
            return MIRInstruction(
                "MAKE_FUNCTION",
                (cast(int, inst.operands[0]) + reg_offset, inst.operands[1]),
                inst.span,
            )
        case _:
            new_ops = tuple(op + reg_offset if isinstance(op, int) else op for op in inst.operands)
            return MIRInstruction(inst.opcode, new_ops, inst.span)


def _offset_terminator(
    term: MIRTerminator,
    reg_offset: int,
    block_offset: int,
) -> MIRTerminator:
    match term.opcode:
        case "JUMP":
            return MIRTerminator("JUMP", (cast(int, term.operands[0]) + block_offset,), term.span)
        case "BRANCH":
            cond, true_b, false_b = term.operands
            return MIRTerminator(
                "BRANCH",
                (
                    cast(int, cond) + reg_offset,
                    cast(int, true_b) + block_offset,
                    cast(int, false_b) + block_offset,
                ),
                term.span,
            )
        case "TAIL_CALL":
            fn_reg, arg_regs = term.operands
            return MIRTerminator(
                "TAIL_CALL",
                (
                    cast(int, fn_reg) + reg_offset,
                    tuple(cast(int, a) + reg_offset for a in cast(tuple, arg_regs)),
                ),
                term.span,
            )
        case _:
            return term


def _remap_fn_indices(fn: MIRFunction, index_map: dict[int, int]) -> MIRFunction:
    new_blocks: list[MIRBlock] = []
    changed = False
    for block in fn.blocks:
        new_instructions: list[MIRInstruction] = []
        for inst in block.instructions:
            if inst.opcode == "MAKE_FUNCTION":
                old_idx = inst.operands[1]
                if isinstance(old_idx, int) and old_idx in index_map:
                    new_instructions.append(
                        MIRInstruction(
                            "MAKE_FUNCTION", (inst.operands[0], index_map[old_idx]), inst.span
                        )
                    )
                    changed = True
                    continue
            new_instructions.append(inst)
        new_blocks.append(MIRBlock(block.id, tuple(new_instructions), block.terminator))

    if not changed:
        return fn
    return MIRFunction(fn.name, fn.params, fn.register_count, tuple(new_blocks), fn.entry)
