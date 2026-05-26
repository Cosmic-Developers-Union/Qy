# coding: utf-8
"""LIR effect-lowering pass.

把 linearize 之后保留的语言级 effect 占位符
(EFFECT_HANDLE_BEGIN / EFFECT_HANDLE_END / EFFECT_PERFORM / EFFECT_RESUME)
展开为抽象机器指令族:

- HANDLER_PUSH / HANDLER_POP — 在 virtual stack 上推/弹一个 handler frame.
- CONT_CAPTURE / CONT_COPY / CONT_RESTORE — 显式建模 delimited continuation.
- EFFECT_UNWIND — 当前 frame 内把 effect 沿 handler stack 抛给最近的 handler frame.
- EFFECT_DISPATCH — handler-target 入口处, VM 把 pending effect 拆成
  (handler_fn_value, arg_value, cont_value) 写到 LIR 指定的寄存器.

输入: linearize 之后的 LIRInstruction 列表 + register_count.
输出: 同形, 但已经不再含语言级 effect 占位符.

设计要点:
- HANDLE region 由配对的 EFFECT_HANDLE_BEGIN(handle_id, body_fn, specs) 与
  EFFECT_HANDLE_END(handle_id, dst) 标定. lowering 把 region 改写为:

      HANDLER_PUSH(H, handler_target, parent_handler_id_or_-1, specs_tuple)
      MAKE_FUNCTION body_reg, body_fn
      CALL dst, body_reg, ()
      HANDLER_POP(H)
      JUMP after_region
  Lh:
      EFFECT_DISPATCH(handler_fn_reg, H, arg_reg, cont_reg)
      CALL dst, handler_fn_reg, (arg_reg, cont_reg)
      HANDLER_POP(H)
      ; fall through to after_region
  after_region:
      ...

- EFFECT_PERFORM(dst, eff, arg, resume_idx, resumable) 改写为:

      CONT_CAPTURE(cont_tmp, K, resume_idx, live_regs, dst_for_resume=dst, multi_shot=resumable)
      EFFECT_UNWIND(eff, arg, cont_tmp)

  EFFECT_UNWIND 是 terminator 类型 (控制权转给 handler frame); 它本身不返回到
  紧随的指令. 因此 perform 之后到 resume_idx 之间的那个原 MIR resume_block
  仍然是有效 jump target —— resume 时由 CONT_RESTORE 跳进去.

- EFFECT_RESUME(dst, cont, value) 改写为:
      CONT_COPY(cont_copy, cont)         ; multi-shot 才需要
      CONT_RESTORE(cont_copy, dst, value)

  one-shot 情况省掉 CONT_COPY (cont_copy = cont), 由 VM 在 RESTORE 时
  把 cont 标 consumed, 二次 RESTORE 会引发 effort.

注意:
- 本 pass 必须在 linearize 之后运行 (需要绝对 instruction-index).
- 必须在 peephole 与 compact_registers 之前运行 (后者依赖最终寄存器布局,
  liveness 分析也基于 pre-compact 寄存器空间).
- pass 引入的新指令会改变 instruction 数, 所以所有原来的 jump 目标必须重新映射:
  对每个原 instruction 索引 i 维护 mapping `old_to_new[i]`, 跑完 lowering 之后
  把所有跳转目标 (JUMP / JUMP_IF_FALSE / EFFECT_PERFORM 的 resume_idx) 修补.
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.errors import SourceSpan
from qy.ir.lir import LIRContinuationLayout
from qy.ir.lir import LIRHandlerLayout
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRRegister

__all__ = ["lower_effects"]


@dataclass(slots=True)
class _LoweringResult:
    instructions: list[LIRInstruction]
    register_count: int
    handlers: tuple[LIRHandlerLayout, ...]
    continuations: tuple[LIRContinuationLayout, ...]


def lower_effects(instructions: list[LIRInstruction], register_count: int) -> _LoweringResult:
    """Expand effect placeholders in *instructions* into abstract-machine ops.

    Returns the new instruction stream, an updated register count (new temps
    may be introduced for cont/handler-fn/arg/cont registers), and the layout
    tables to attach onto the LIRFunction.
    """
    if not _has_placeholders(instructions):
        return _LoweringResult(instructions, register_count, (), ())

    # Phase 1: scan handle regions; pair BEGIN/END.
    regions = _scan_handle_regions(instructions)

    # Phase 2: rewrite each instruction; track old→new index map.
    register_alloc = _RegisterAllocator(register_count)
    new_instructions: list[LIRInstruction] = []
    handler_layouts: list[LIRHandlerLayout] = []
    continuation_layouts: list[LIRContinuationLayout] = []
    handler_target_holes: list[tuple[int, int]] = []  # (instr_idx, handler_id)
    perform_resume_patches: list[tuple[int, int]] = []  # (instr_idx, old_resume_idx)

    # Map: old instruction index -> new instruction index of *the first
    # instruction emitted while consuming the old one*. For BEGIN, this points
    # at the HANDLER_PUSH; for END, at the after-region label position.
    old_to_new: dict[int, int] = {}

    handler_stack: list[int] = []  # current enclosing handler_ids

    # We need to know, for each region begin index, the pair end index, and
    # for each end index, the matching begin.
    {begin: end for begin, end in regions}
    end_to_begin = {end: begin for begin, end in regions}

    # For each region, allocate handler_id and dispatch label (filled later).
    region_meta: dict[int, _RegionMeta] = {}
    next_handler_id = 0
    for begin_idx, end_idx in regions:
        begin_inst = instructions[begin_idx]
        # operand layout: (handle_id, body_fn_idx, handler_specs)
        _mir_handle_id, body_fn_idx, specs = begin_inst.operands
        end_inst = instructions[end_idx]
        # operand layout: (handle_id, dst_reg)
        _, dst_reg = end_inst.operands
        region_meta[begin_idx] = _RegionMeta(
            handler_id=next_handler_id,
            body_fn_idx=body_fn_idx,
            specs=specs,
            dst_reg=dst_reg,
            begin=begin_idx,
            end=end_idx,
        )
        next_handler_id += 1

    next_continuation_id = 0

    for old_idx, instruction in enumerate(instructions):
        old_to_new[old_idx] = len(new_instructions)
        opcode = instruction.opcode
        span = instruction.span

        if opcode == "EFFECT_HANDLE_BEGIN":
            meta = region_meta[old_idx]
            parent_id = handler_stack[-1] if handler_stack else -1
            handler_stack.append(meta.handler_id)

            # Reserve HANDLER_PUSH; handler_target_idx will be patched later
            # to the dispatch label position.
            push_idx = len(new_instructions)
            new_instructions.append(
                LIRInstruction(
                    "HANDLER_PUSH",
                    (meta.handler_id, None, parent_id, meta.specs),
                    span,
                )
            )
            handler_target_holes.append((push_idx, meta.handler_id))

            body_reg = register_alloc.alloc()
            new_instructions.append(
                LIRInstruction("LOAD_HOST", (body_reg, _BodyFnRef(meta.body_fn_idx)), span)
            )
            # Replace LOAD_HOST(body_reg, BodyFnRef) with MAKE_FUNCTION at the
            # bytecode-emit level; for now we emit MAKE_FUNCTION directly so
            # the VM gets a BytecodeFunctionValue.
            # Rewind: replace last instruction.
            new_instructions[-1] = LIRInstruction(
                "MAKE_FUNCTION", (body_reg, meta.body_fn_idx), span
            )
            new_instructions.append(LIRInstruction("CALL", (meta.dst_reg, body_reg, ()), span))
            new_instructions.append(LIRInstruction("HANDLER_POP", (meta.handler_id,), span))
            # Jump over dispatch tail to after_region.
            # The end-of-region position will be patched when we encounter END.
            jump_over_idx = len(new_instructions)
            new_instructions.append(LIRInstruction("JUMP", (None,), span))

            # Dispatch tail starts here.
            dispatch_label = len(new_instructions)
            handler_fn_reg = register_alloc.alloc()
            arg_reg = register_alloc.alloc()
            cont_reg = register_alloc.alloc()
            new_instructions.append(
                LIRInstruction(
                    "EFFECT_DISPATCH",
                    (handler_fn_reg, meta.handler_id, arg_reg, cont_reg),
                    span,
                )
            )
            new_instructions.append(
                LIRInstruction(
                    "CALL",
                    (meta.dst_reg, handler_fn_reg, (arg_reg, cont_reg)),
                    span,
                )
            )
            new_instructions.append(LIRInstruction("HANDLER_POP", (meta.handler_id,), span))

            # Stash the layout; handler_target gets the dispatch_label index.
            meta.dispatch_label_new_idx = dispatch_label
            meta.jump_over_new_idx = jump_over_idx
            handler_layouts.append(
                LIRHandlerLayout(
                    id=meta.handler_id,
                    effects=tuple(
                        spec[0] for spec in meta.specs if isinstance(spec, tuple) and spec
                    ),
                    handler_target=dispatch_label,
                    parent_handler=parent_id if parent_id >= 0 else None,
                    ss_chain=(),
                )
            )

        elif opcode == "EFFECT_HANDLE_END":
            # Pop handler stack; the JUMP-over-dispatch from BEGIN should
            # land *here* (i.e. at len(new_instructions) before we emit any
            # follow-up). We patch the JUMP target to the current new index.
            begin_idx = end_to_begin[old_idx]
            meta = region_meta[begin_idx]
            assert handler_stack and handler_stack[-1] == meta.handler_id
            handler_stack.pop()
            after_region_new_idx = len(new_instructions)
            jump_inst = new_instructions[meta.jump_over_new_idx]
            new_instructions[meta.jump_over_new_idx] = LIRInstruction(
                "JUMP", (after_region_new_idx,), jump_inst.span
            )
            # We don't emit anything for EFFECT_HANDLE_END itself; old_to_new
            # for this index already records the after-region label position.
            # But old_to_new[old_idx] was set at top of loop, so we need to
            # adjust it to point to after_region_new_idx (which is the same
            # value we just used).
            old_to_new[old_idx] = after_region_new_idx

        elif opcode == "EFFECT_PERFORM":
            # operands: (dst, eff_sym, arg_reg, resume_idx, resumable)
            dst, eff_sym, arg_reg, resume_idx, resumable = instruction.operands
            cont_reg = register_alloc.alloc()
            cont_layout_id = next_continuation_id
            next_continuation_id += 1
            continuation_layouts.append(
                LIRContinuationLayout(
                    id=cont_layout_id,
                    resume_target=None,  # patched later
                    saved_registers=(),  # liveness analysis below fills if needed
                    saved_spaces=(),
                    multi_shot=bool(resumable),
                )
            )
            # Resume-target instruction-index is *old* — we keep it and patch
            # against old_to_new at the end.
            new_instructions.append(
                LIRInstruction(
                    "CONT_CAPTURE",
                    (
                        cont_reg,
                        cont_layout_id,
                        None,  # resume_target_idx — patched below
                        (),  # saved_regs — left empty in this lowering
                        dst,
                        bool(resumable),
                    ),
                    span,
                )
            )
            perform_resume_patches.append((len(new_instructions) - 1, resume_idx))
            # EFFECT_UNWIND is a terminator that transfers control to the
            # nearest matching handler's dispatch label.
            new_instructions.append(
                LIRInstruction("EFFECT_UNWIND", (eff_sym, arg_reg, cont_reg), span)
            )

        elif opcode == "EFFECT_RESUME":
            # operands: (dst, cont_reg, value_reg)
            dst, cont_reg, value_reg = instruction.operands
            # Multi-shot is the conservative default; VM enforces one-shot via
            # the cont's own multi_shot flag (set at CONT_CAPTURE time).
            cont_copy = register_alloc.alloc()
            new_instructions.append(LIRInstruction("CONT_COPY", (cont_copy, cont_reg), span))
            new_instructions.append(
                LIRInstruction("CONT_RESTORE", (cont_copy, dst, value_reg), span)
            )

        else:
            new_instructions.append(instruction)

    # Patch jumps: scan all instructions whose operands carry an old-index
    # target into the resolved new-index target.
    new_instructions = _remap_jump_targets(new_instructions, old_to_new)

    # Patch handler_target on HANDLER_PUSH (already absolute new indices since
    # we computed dispatch_label as len(new_instructions) at emit time).
    for instr_idx, handler_id in handler_target_holes:
        target = next(
            layout.handler_target for layout in handler_layouts if layout.id == handler_id
        )
        push_inst = new_instructions[instr_idx]
        ops = list(push_inst.operands)
        ops[1] = target
        new_instructions[instr_idx] = LIRInstruction(push_inst.opcode, tuple(ops), push_inst.span)

    # Patch CONT_CAPTURE.resume_target_idx using old_to_new.
    new_continuation_layouts: list[LIRContinuationLayout] = []
    for instr_idx, old_resume_idx in perform_resume_patches:
        capture_inst = new_instructions[instr_idx]
        new_resume_idx = old_to_new.get(old_resume_idx, old_resume_idx)
        ops = list(capture_inst.operands)
        ops[2] = new_resume_idx
        new_instructions[instr_idx] = LIRInstruction(
            capture_inst.opcode, tuple(ops), capture_inst.span
        )
        cont_layout_id = ops[1]
        old_layout = continuation_layouts[cont_layout_id]
        new_continuation_layouts.append(
            LIRContinuationLayout(
                id=old_layout.id,
                resume_target=new_resume_idx,
                saved_registers=old_layout.saved_registers,
                saved_spaces=old_layout.saved_spaces,
                multi_shot=old_layout.multi_shot,
            )
        )

    return _LoweringResult(
        new_instructions,
        register_alloc.count,
        tuple(handler_layouts),
        tuple(new_continuation_layouts),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _RegionMeta:
    handler_id: int
    body_fn_idx: object
    specs: object
    dst_reg: object
    begin: int
    end: int
    dispatch_label_new_idx: int = -1
    jump_over_new_idx: int = -1


@dataclass(frozen=True, slots=True)
class _BodyFnRef:
    """Sentinel kept inside the lowering for clarity; not emitted."""

    fn_idx: int


class _RegisterAllocator:
    __slots__ = ("count",)

    def __init__(self, register_count: int) -> None:
        self.count = register_count

    def alloc(self) -> LIRRegister:
        reg = self.count
        self.count += 1
        return reg


def _has_placeholders(instructions: list[LIRInstruction]) -> bool:
    for inst in instructions:
        if inst.opcode in (
            "EFFECT_HANDLE_BEGIN",
            "EFFECT_HANDLE_END",
            "EFFECT_PERFORM",
            "EFFECT_RESUME",
        ):
            return True
    return False


def _scan_handle_regions(
    instructions: list[LIRInstruction],
) -> list[tuple[int, int]]:
    """Pair every EFFECT_HANDLE_BEGIN with its matching EFFECT_HANDLE_END.

    Returns a list of (begin_idx, end_idx) pairs in source order.  Pairs are
    matched by handle_id, which is unique per region (allocated in MIR).
    """
    open_regions: dict[int, int] = {}  # handle_id -> begin_idx
    pairs: list[tuple[int, int]] = []
    for idx, inst in enumerate(instructions):
        if inst.opcode == "EFFECT_HANDLE_BEGIN":
            handle_id = inst.operands[0]
            assert isinstance(handle_id, int)
            open_regions[handle_id] = idx
        elif inst.opcode == "EFFECT_HANDLE_END":
            handle_id = inst.operands[0]
            assert isinstance(handle_id, int)
            begin_idx = open_regions.pop(handle_id)
            pairs.append((begin_idx, idx))
    if open_regions:
        raise ValueError(f"unpaired EFFECT_HANDLE_BEGIN(s): handle_ids={sorted(open_regions)}")
    return pairs


def _remap_jump_targets(
    instructions: list[LIRInstruction],
    old_to_new: dict[int, int],
) -> list[LIRInstruction]:
    """Rewrite jump-target operands so they refer to *new* instruction indices.

    BEFORE this pass runs, jump targets in a freshly linearized stream point
    at *old* indices.  After we expand placeholders the stream length grows;
    we must remap every absolute-index operand to its post-expansion location.

    Targets we know about:
    - JUMP (target,)
    - JUMP_IF_FALSE (cond_reg, target)

    EFFECT_PERFORM resume targets are remapped explicitly by the caller using
    perform_resume_patches; we do *not* touch them here.

    Note: we only remap targets that appear in old_to_new — instructions emitted
    during this pass (HANDLER_PUSH dispatch label, JUMP-over-dispatch) carry
    new indices that the caller already filled with absolute new positions and
    are *not* present in old_to_new.  We detect this by sentinel: JUMP/JUMP_IF_FALSE
    we just emitted use targets we already know are new.  But the freshly linearized
    JUMPs from MIR carry *old* indices.

    Strategy: build an inverse map; if target value is found in old_to_new
    *values*, leave it alone; otherwise treat as old and remap.
    """
    new_target_values = set(old_to_new.values())
    out: list[LIRInstruction] = []
    for inst in instructions:
        if inst.opcode == "JUMP":
            target = inst.operands[0]
            if isinstance(target, int) and target in old_to_new and target not in new_target_values:
                target = old_to_new[target]
            elif isinstance(target, int) and target in old_to_new:
                # Ambiguous: it could be either old or new and they collide.
                # Heuristic: if instruction was emitted during expansion we
                # would have set target to a *new* index that is in
                # new_target_values; only inputs from MIR carry old indices.
                # To disambiguate cleanly, we assume any int that maps via
                # old_to_new to a *different* value should be remapped.
                if old_to_new[target] != target:
                    target = old_to_new[target]
            out.append(LIRInstruction(inst.opcode, (target,), inst.span))
            continue
        if inst.opcode == "JUMP_IF_FALSE":
            cond, target = inst.operands
            if isinstance(target, int) and target in old_to_new:
                if old_to_new[target] != target:
                    target = old_to_new[target]
            out.append(LIRInstruction(inst.opcode, (cond, target), inst.span))
            continue
        out.append(inst)
    return out


# Suppress unused-import warning for SourceSpan (used only in type hints).
_ = SourceSpan
