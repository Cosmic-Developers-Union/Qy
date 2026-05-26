# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""LIR verifier 目标模块。.

目标：
- 校验 LIR control、register、frame、handler、slot、debug metadata 的一致性。
- 成为 LIR -> bytecode / LLVM 之前的结构门。

禁止：
- verifier 不得重写程序；rewrite 应属于 passes。
"""

from __future__ import annotations

from qy.diag import Diagnostic
from qy.ir.lir.node import LIRProgram

__all__ = ["verify_lir"]

_TERMINATORS = frozenset({"RETURN", "TAIL_CALL", "RAISE_EFFECT", "CONT_RESTORE", "EFFECT_UNWIND"})
_JUMP_OPCODES = frozenset({"JUMP", "JUMP_IF_FALSE", "BRANCH_NIL"})

# Opcodes that split an IR-level uninterruptible point in LIR — they must not
# appear adjacent to a continuous instruction within the same linearized stream.
_CONTINUOUS_BREAK_OPCODES = frozenset(
    {
        "ENTER_SCOPE",
        "EXIT_SCOPE",
        "SS_ENTER",
        "SS_LEAVE",
        "SS_RESTORE",
        "FRAME_ENTER",
        "FRAME_LEAVE",
        "HANDLER_PUSH",
        "HANDLER_POP",
        "EFFECT_UNWIND",
        "EFFECT_DISPATCH",
        "CONT_CAPTURE",
        "CONT_COPY",
        "CONT_RESTORE",
        "CONT_INJECT",
        "DEFEFFECT",
        "DEFINE_MODULE",
        "FROM_IMPORT",
        "RUNTIME_EVAL",
        "CACHE_EVAL",
        "ALL_GATHER",
        "PARALLEL_GATHER",
        "RACE_FIRST",
        "JUMP",
        "JUMP_IF_FALSE",
        "BRANCH_NIL",
        "RETURN",
        "TAIL_CALL",
        "RAISE_EFFECT",
    }
)


def verify_lir(program: LIRProgram) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for func in program.functions:
        if not func.instructions and func.name.name not in ("<lambda>",):
            diagnostics.append(
                Diagnostic(f"LIR function {func.name.name} has no instructions", severity="warning")
            )
            continue

        saw_terminator = False
        for idx, inst in enumerate(func.instructions):
            if saw_terminator:
                diagnostics.append(
                    Diagnostic(
                        f"LIR function {func.name.name} has unreachable instruction "
                        f"{inst.opcode} at {idx} after terminator",
                        severity="warning",
                    )
                )
                break
            if inst.opcode in _TERMINATORS:
                saw_terminator = True

        if not saw_terminator:
            last_opcode = func.instructions[-1].opcode
            diagnostics.append(
                Diagnostic(
                    f"LIR function {func.name.name} does not end with a terminator "
                    f"(last instruction: {last_opcode})",
                    severity="error",
                )
            )

        for idx, inst in enumerate(func.instructions):
            if inst.opcode in {"PERFORM", "HANDLE", "RESUME"}:
                diagnostics.append(
                    Diagnostic(
                        f"LIR function {func.name.name} retains language-level "
                        f"effect opcode {inst.opcode} at {idx}; effects must be "
                        "lowered to abstract-machine opcodes (HANDLER_PUSH/POP, "
                        "CONT_*, EFFECT_UNWIND/DISPATCH)",
                        severity="error",
                    )
                )
            if inst.opcode in {
                "EFFECT_HANDLE_BEGIN",
                "EFFECT_HANDLE_END",
                "EFFECT_PERFORM",
                "EFFECT_RESUME",
            }:
                diagnostics.append(
                    Diagnostic(
                        f"LIR function {func.name.name} retains MIR-level effect "
                        f"placeholder {inst.opcode} at {idx}; the effect-lowering "
                        "pass must eliminate all EFFECT_HANDLE_*/EFFECT_PERFORM/EFFECT_RESUME",
                        severity="error",
                    )
                )
            if inst.opcode == "LOAD_HOST" and len(inst.operands) >= 2 and inst.operands[1] is None:
                diagnostics.append(
                    Diagnostic(
                        f"LIR LOAD_HOST None at {func.name.name}:{idx} should be LOAD_NIL",
                        severity="warning",
                    )
                )
            for operand in _register_operands_of(inst.opcode, inst.operands):
                if not isinstance(operand, int):
                    continue
                if operand < 0 or operand >= func.register_count:
                    diagnostics.append(
                        Diagnostic(
                            f"LIR function {func.name.name} uses out-of-range register r{operand} "
                            f"(register_count={func.register_count})",
                            severity="error",
                        )
                    )
            if inst.opcode in _JUMP_OPCODES and len(inst.operands) >= 1:
                target = inst.operands[-1]
                if isinstance(target, int):
                    if target < 0 or target >= len(func.instructions):
                        diagnostics.append(
                            Diagnostic(
                                f"LIR function {func.name.name} has jump to out-of-range target {target}",
                                severity="error",
                            )
                        )

        _verify_continuous_run(func, diagnostics)
    return tuple(diagnostics)


def _verify_continuous_run(func: object, diagnostics: list[Diagnostic]) -> None:
    """Continuous instructions in LIR must not be adjacent to break-point opcodes.

    Linearization, peephole and jump-fixup passes are allowed to reorder /
    coalesce regular instructions, but they may not split an IR-level
    uninterruptible point by inserting (or relocating) a control-flow,
    scope-chain transition, or effect-frame opcode next to it.
    """
    instructions = getattr(func, "instructions", ())
    name = getattr(getattr(func, "name", None), "name", "<anonymous>")
    for index, inst in enumerate(instructions):
        if not getattr(inst, "continuous", False):
            continue

        if inst.opcode in _CONTINUOUS_BREAK_OPCODES:
            diagnostics.append(
                Diagnostic(
                    f"LIR function {name} marks break-point opcode {inst.opcode} "
                    f"at {index} as continuous; continuous instructions must not "
                    "be break-points themselves",
                    severity="error",
                )
            )

        if index > 0:
            prev = instructions[index - 1]
            if prev.opcode in _CONTINUOUS_BREAK_OPCODES:
                diagnostics.append(
                    Diagnostic(
                        f"LIR function {name} places break-point {prev.opcode} "
                        f"immediately before continuous instruction {inst.opcode} "
                        f"at {index}; continuous run was split by a pass",
                        severity="error",
                    )
                )

        if index + 1 < len(instructions):
            nxt = instructions[index + 1]
            if nxt.opcode in _CONTINUOUS_BREAK_OPCODES:
                diagnostics.append(
                    Diagnostic(
                        f"LIR function {name} places break-point {nxt.opcode} "
                        f"immediately after continuous instruction {inst.opcode} "
                        f"at {index}; continuous run was split by a pass",
                        severity="error",
                    )
                )


def _register_operands_of(opcode: str, operands: tuple[object, ...]) -> list[object]:
    match opcode:
        case "LOAD_HOST" | "LOAD_NIL" | "LOAD_T" | "LOAD_ENV" | "RETURN" | "APPEND_RESULT":
            return [operands[0]] if operands else []
        case "SLOT_READ" | "SS_LOOKUP" | "SLOT_PENDING_EFFORT":
            return [operands[0]] if operands else []
        case "SLOT_COMPLETE":
            return [operands[1]] if len(operands) >= 2 else []
        case "MOVE":
            return list(operands) if len(operands) >= 2 else []
        case "DEFINE_ONCE":
            return [operands[1]] if len(operands) >= 2 else []
        case "MAKE_FUNCTION" | "MAKE_MACRO":
            return [operands[0]] if operands else []
        case "CALL":
            regs = [operands[0], operands[1]] if len(operands) >= 2 else []
            if len(operands) >= 3 and isinstance(operands[2], tuple):
                regs.extend(operands[2])
            return regs
        case "TAIL_CALL":
            regs = [operands[0]] if operands else []
            if len(operands) >= 2 and isinstance(operands[1], tuple):
                regs.extend(operands[1])
            return regs
        case "BUILD_TUPLE":
            return list(operands)
        case "APPLY" | "RUNTIME_EVAL":
            return list(operands)
        case "JUMP_IF_FALSE":
            return [operands[0]] if operands else []
        case "RAISE_EFFECT":
            return [operands[1]] if len(operands) >= 2 else []
        case "CONT_CAPTURE":
            # operands: (dst_cont_reg, cont_layout_id, resume_target_idx,
            #            saved_regs_tuple, dst_reg_for_resume, multi_shot)
            regs = [operands[0]] if operands else []
            if len(operands) >= 4 and isinstance(operands[3], tuple):
                regs.extend(operands[3])
            if len(operands) >= 5:
                regs.append(operands[4])
            return regs
        case "CONT_COPY":
            return [operands[0], operands[1]] if len(operands) >= 2 else list(operands)
        case "CONT_RESTORE":
            # operands: (cont_reg, dst_reg_after_resume, value_reg)
            return list(operands[:3]) if len(operands) >= 3 else list(operands)
        case "CONT_INJECT":
            return [operands[0], operands[1]] if len(operands) >= 2 else list(operands)
        case "EFFECT_UNWIND":
            # operands: (effect_sym, arg_reg, cont_reg)
            regs: list[object] = []
            if len(operands) >= 2:
                regs.append(operands[1])
            if len(operands) >= 3:
                regs.append(operands[2])
            return regs
        case "EFFECT_DISPATCH":
            # operands: (dst_handler_fn_reg, handler_id, arg_dst_reg, cont_dst_reg)
            regs: list[object] = []
            if operands:
                regs.append(operands[0])
            if len(operands) >= 3:
                regs.append(operands[2])
            if len(operands) >= 4:
                regs.append(operands[3])
            return regs
        case "HANDLER_PUSH" | "HANDLER_POP":
            return []
        case "FRAME_ENTER" | "FRAME_LEAVE":
            return []
        case "SS_ENTER" | "SS_LEAVE" | "SS_RESTORE" | "SS_COPY":
            return []
        case "EFFECT_PERFORM":
            # placeholder: (dst_reg, effect_sym, arg_reg, resume_idx, resumable)
            regs: list[object] = []
            if operands:
                regs.append(operands[0])
            if len(operands) >= 3:
                regs.append(operands[2])
            return regs
        case "EFFECT_HANDLE_BEGIN":
            # placeholder: (handle_id, body_fn_idx, handler_specs)
            return []
        case "EFFECT_HANDLE_END":
            # placeholder: (handle_id, dst_reg)
            return [operands[1]] if len(operands) >= 2 else []
        case "EFFECT_RESUME":
            # placeholder: (dst_reg, cont_reg, value_reg)
            return list(operands[:3])
        case "CACHE_EVAL":
            return [operands[0]] if operands else []
        case "DEFINE_MODULE":
            return [operands[0]] if operands else []
        case "PARALLEL_GATHER" | "ALL_GATHER" | "RACE_FIRST":
            return [operands[0]] if operands else []
        case _:
            return []
