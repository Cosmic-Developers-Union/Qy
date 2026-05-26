# coding: utf-8
"""LIR compat-effects pass.

把 linearize 之后保留的 MIR effect 占位符
(EFFECT_HANDLE_BEGIN / EFFECT_HANDLE_END / EFFECT_PERFORM / EFFECT_RESUME)
折叠成 register VM 可执行的语言级 effect 指令:

- EFFECT_HANDLE_BEGIN h body_fn specs + EFFECT_HANDLE_END h dst
  → HANDLE dst body_fn specs (END 指令位置消失)
- EFFECT_PERFORM dst eff arg resume_idx resumable
  → PERFORM dst eff arg, 必要时追加 JUMP resume_idx
- EFFECT_RESUME dst cont value → RESUME dst cont value

指令数量变化后, 所有原 jump target (JUMP / JUMP_IF_FALSE / EFFECT_PERFORM
resume_idx) 必须被重新映射到新位置.

输入: linearize 之后的 LIRInstruction 列表 (compat 路径).
输出: 同形, 但已经不再含 EFFECT_* 占位符, 改成 HANDLE/PERFORM/RESUME.

注意: 这是 compat dialect 的降级路径, 服务于 register VM bytecode 后端.
abstract-machine dialect 应该走 ``effects.lower_effects``, 把占位符展开成
HANDLER_PUSH / CONT_* / EFFECT_DISPATCH/UNWIND.
"""

from __future__ import annotations

from qy.ir.lir import LIRInstruction

__all__ = ["lower_compat_effects"]


def lower_compat_effects(instructions: list[LIRInstruction]) -> list[LIRInstruction]:
    if not _has_placeholders(instructions):
        return instructions

    end_indices: set[int] = set()
    begin_to_end: dict[int, int] = {}
    open_begins: dict[object, int] = {}
    for idx, inst in enumerate(instructions):
        if inst.opcode == "EFFECT_HANDLE_BEGIN":
            handle_id = inst.operands[0]
            open_begins[handle_id] = idx
        elif inst.opcode == "EFFECT_HANDLE_END":
            handle_id = inst.operands[0]
            begin_idx = open_begins.pop(handle_id)
            begin_to_end[begin_idx] = idx
            end_indices.add(idx)
    if open_begins:
        raise ValueError(
            f"unpaired EFFECT_HANDLE_BEGIN(s): handle_ids={sorted(open_begins.values())}"
        )

    old_to_new: dict[int, int] = {}
    new_instructions: list[LIRInstruction] = []
    extra_perform_jumps: list[tuple[int, int]] = []

    for old_idx, inst in enumerate(instructions):
        old_to_new[old_idx] = len(new_instructions)
        opcode = inst.opcode
        if opcode == "EFFECT_HANDLE_BEGIN":
            _handle_id, body_fn_idx, specs = inst.operands
            end_inst = instructions[begin_to_end[old_idx]]
            _, dst_reg = end_inst.operands
            new_instructions.append(
                LIRInstruction("HANDLE", (dst_reg, body_fn_idx, specs), inst.span)
            )
        elif opcode == "EFFECT_HANDLE_END":
            old_to_new[old_idx] = len(new_instructions)
        elif opcode == "EFFECT_PERFORM":
            dst, eff_sym, arg_reg, resume_idx, _resumable = inst.operands
            new_instructions.append(LIRInstruction("PERFORM", (dst, eff_sym, arg_reg), inst.span))
            jump_new_idx = len(new_instructions)
            new_instructions.append(LIRInstruction("JUMP", (None,), inst.span))
            assert isinstance(resume_idx, int)
            extra_perform_jumps.append((jump_new_idx, resume_idx))
        elif opcode == "EFFECT_RESUME":
            dst, cont_reg, value_reg = inst.operands
            new_instructions.append(LIRInstruction("RESUME", (dst, cont_reg, value_reg), inst.span))
        else:
            new_instructions.append(inst)

    perform_jump_indices: set[int] = set()
    for jump_idx, old_resume_idx in extra_perform_jumps:
        new_target = old_to_new[old_resume_idx]
        jump_inst = new_instructions[jump_idx]
        new_instructions[jump_idx] = LIRInstruction("JUMP", (new_target,), jump_inst.span)
        perform_jump_indices.add(jump_idx)

    out: list[LIRInstruction] = []
    for new_idx, inst in enumerate(new_instructions):
        if inst.opcode == "JUMP" and new_idx not in perform_jump_indices:
            (target,) = inst.operands
            if isinstance(target, int):
                remapped = old_to_new.get(target, target)
                inst = LIRInstruction("JUMP", (remapped,), inst.span)
        elif inst.opcode == "JUMP_IF_FALSE":
            cond, target = inst.operands
            if isinstance(target, int):
                remapped = old_to_new.get(target, target)
                inst = LIRInstruction("JUMP_IF_FALSE", (cond, remapped), inst.span)
        out.append(inst)

    skip_indices: set[int] = set()
    for jump_idx, _ in extra_perform_jumps:
        target_inst = out[jump_idx]
        if target_inst.opcode == "JUMP":
            (target,) = target_inst.operands
            if isinstance(target, int) and target == jump_idx + 1:
                skip_indices.add(jump_idx)

    if not skip_indices:
        return out

    shift_map: dict[int, int] = {}
    new_pos = 0
    for old_pos in range(len(out)):
        shift_map[old_pos] = new_pos
        if old_pos in skip_indices:
            continue
        new_pos += 1

    elided: list[LIRInstruction] = []
    for old_pos, inst in enumerate(out):
        if old_pos in skip_indices:
            continue
        if inst.opcode == "JUMP":
            (target,) = inst.operands
            if isinstance(target, int):
                inst = LIRInstruction("JUMP", (shift_map[target],), inst.span)
        elif inst.opcode == "JUMP_IF_FALSE":
            cond, target = inst.operands
            if isinstance(target, int):
                inst = LIRInstruction("JUMP_IF_FALSE", (cond, shift_map[target]), inst.span)
        elided.append(inst)

    return elided


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
