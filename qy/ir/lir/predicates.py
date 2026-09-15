# -*- coding: utf-8 -*-
"""LIR well-formedness predicates (L1-L15).

每个谓词对应 `docs/lir-spec.md` §4 中编号为 L1..L15 的一条不变量。
Phase 1 的范围：

- **L1, L4, L13, L15**：已由 :mod:`qy.ir.lir.verify` 的 ``verify_lir`` 实施；
  本模块暴露其纯谓词形态便于测试与单独调用。
- **L2, L5..L12, L14**：在 Phase 1 中首次实现为纯谓词；当前生产 LIR
  大部分 layout 字段未填充（lir-spec.md §7.8），所以 L5..L12 目前总是返回
  空诊断；这是有意为之的 future-proof（见 plan decision (b)）。

设计要点：

- 所有谓词是**纯函数**；不修改 IR、不重写指令流。
- :func:`check_program` 是 Phase 1 中 :func:`verify_lir` 的扩展入口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qy.diag import Diagnostic
from qy.diag import Severity

if TYPE_CHECKING:
    from qy.ir.lir.frame import LIRFrameLayout
    from qy.ir.lir.node import LIRFunction
    from qy.ir.lir.node import LIRProgram


__all__ = [
    "check_program",
    "l2_unique_function_ids",
    "l5_frame_layout_consistent",
    "l6_continuation_layout_consistent",
    "l7_handler_parent_exists",
    "l8_slot_address_in_space",
    "l9_slot_complete_at_most_once",
    "l10_scope_nesting",
    "l11_handler_push_pop_nesting",
    "l12_frame_enter_leave_nesting",
    "l14_compat_no_abstract_machine_opcodes",
]


# ─── L2 ──────────────────────────────────────────────────────────────────────
# "function ids 唯一；main 有效"


def l2_unique_function_ids(program: LIRProgram) -> tuple[Diagnostic, ...]:
    """校验 LIRProgram 中各函数的 function_id 不重复。.

    当前 :class:`LIRFunction` 没有显式 ``id`` 字段；function id 由 functions
    tuple 的下标承担。本谓词等价于 ``len(set(id(f) for f in functions)) ==
    len(functions)``，并在 main 越界时报错。
    """
    # tuple 索引天然唯一；这里只校验 main。
    if program.main < 0 or program.main >= len(program.functions):
        return (
            Diagnostic(
                f"LIR main function index {program.main} is out of range "
                f"for {len(program.functions)} LIR functions"
            ),
        )
    return ()


# ─── L5..L9 ──────────────────────────────────────────────────────────────────
# "Frame/Handler/Continuation/Slot layout 完整性"
#
# 当前生产 LIR 几乎不填充 layout 字段（lir-spec.md §7.8）。Phase 1 中 L5..L9
# 实现为"如果 layout 不空则校验，否则跳过"，这样未来 symbol_space_layout /
# binding_lowering 落地后 verifier 会自动启用检查，而无需再改 verifier 代码。


def l5_frame_layout_consistent(func: LIRFunction) -> tuple[Diagnostic, ...]:
    layout: LIRFrameLayout | None = getattr(func, "frame_layout", None)
    if layout is None:
        return ()
    out: list[Diagnostic] = []
    if layout.register_count < 0:
        out.append(
            Diagnostic(f"LIR function {func.name.name} frame_layout has negative register_count")
        )
    if layout.local_slot_count < 0:
        out.append(
            Diagnostic(f"LIR function {func.name.name} frame_layout has negative local_slot_count")
        )
    # saved_registers 全部在 [0, layout.register_count) 内
    for reg in layout.saved_registers:
        if reg < 0 or reg >= layout.register_count:
            out.append(
                Diagnostic(
                    f"LIR function {func.name.name} frame_layout saved_register "
                    f"{reg} out of range (register_count={layout.register_count})"
                )
            )
    return tuple(out)


def l6_continuation_layout_consistent(func: LIRFunction) -> tuple[Diagnostic, ...]:
    """Continuations 字段（如有）应满足：saved_registers 与函数 register_count 一致。."""
    continuations = getattr(func, "continuations", ())
    if not continuations:
        return ()
    out: list[Diagnostic] = []
    for cont in continuations:
        for reg in cont.saved_registers:
            if reg < 0 or reg >= func.register_count:
                out.append(
                    Diagnostic(
                        f"LIR function {func.name.name} continuation {cont.id} "
                        f"saved_register {reg} out of range "
                        f"(register_count={func.register_count})"
                    )
                )
    return tuple(out)


def l7_handler_parent_exists(program: LIRProgram) -> tuple[Diagnostic, ...]:
    """handler.parent_handler 必须指向同一 program 中已存在的 handler。."""
    from typing import cast

    from qy.ir.lir.frame import LIRHandlerLayout

    out: list[Diagnostic] = []
    handler_ids: set[int] = set()
    all_handlers: list[tuple[str, LIRHandlerLayout]] = []
    for func in program.functions:
        for handler in getattr(func, "handlers", ()):
            typed = cast(LIRHandlerLayout, handler)
            handler_ids.add(typed.id)
            all_handlers.append((func.name.name, typed))

    for func_name, handler in all_handlers:
        if handler.parent_handler is None:
            continue
        if handler.parent_handler not in handler_ids:
            out.append(
                Diagnostic(
                    f"LIR function {func_name} handler {handler.id} parent_handler "
                    f"{handler.parent_handler} does not exist in program"
                )
            )
    return tuple(out)


def l8_slot_address_in_space(program: LIRProgram) -> tuple[Diagnostic, ...]:
    """slot.address 必须指向 program 中已存在的 symbol space。."""
    from typing import cast

    from qy.ir.lir.frame import LIRSymbolSpaceLayout
    from qy.ir.lir.node import LIRBindingSlot

    out: list[Diagnostic] = []
    space_ids: set[int] = set()
    all_slots: list[tuple[str, LIRBindingSlot]] = []
    for func in program.functions:
        for space in getattr(func, "symbol_spaces", ()):
            typed_space = cast(LIRSymbolSpaceLayout, space)
            space_ids.add(typed_space.id)
            for slot in typed_space.slots:
                all_slots.append((func.name.name, slot))

    for func_name, slot in all_slots:
        addr = slot.address
        addr_space = getattr(addr, "space", addr)
        if addr_space not in space_ids:
            slot_name = slot.symbol.name
            out.append(
                Diagnostic(
                    f"LIR function {func_name} slot {slot_name!r} "
                    f"address {addr} does not match any symbol space"
                )
            )
    return tuple(out)


def l9_slot_complete_at_most_once(program: LIRProgram) -> tuple[Diagnostic, ...]:
    """同一 slot 不得被 ``SLOT_COMPLETE`` 多次执行（静态扫描指令流）。.

    ``SLOT_COMPLETE`` 的 operand schema 是 ``(LIRBindingAddr, src_reg)``；
    slot identity 取自 ``address`` 的 ``(space, slot)``。
    """
    out: list[Diagnostic] = []
    for func in program.functions:
        # Slot identity is function-local: space ids are per-function.
        completed: set[tuple[int, int]] = set()
        for inst in func.instructions:
            if inst.opcode != "SLOT_COMPLETE" or not inst.operands:
                continue
            address = inst.operands[0]
            space_id = getattr(address, "space", None)
            slot_idx = getattr(address, "slot", None)
            if not isinstance(space_id, int) or not isinstance(slot_idx, int):
                continue
            key = (space_id, slot_idx)
            if key in completed:
                out.append(
                    Diagnostic(
                        f"LIR function {func.name.name} SLOT_COMPLETE "
                        f"({key[0]}, {key[1]}) executes more than once"
                    )
                )
            completed.add(key)
    return tuple(out)


# ─── L10 ─────────────────────────────────────────────────────────────────────
# "ENTER_SCOPE/EXIT_SCOPE 正确嵌套"


_SCOPE_OPCODES = ("ENTER_SCOPE", "EXIT_SCOPE")


def l10_scope_nesting(func: LIRFunction) -> tuple[Diagnostic, ...]:
    """LIR scope 必须正确嵌套。.

    同 M10：tail-position 的 ``let``/``defun`` body 由 lowerer 故意省略
    ``EXIT_SCOPE``（控制流不会跨函数边界泄漏；运行时 VM 直接丢弃 frame.env），
    因此函数末尾的 unclosed ENTER_SCOPE 在 LIR 中也合法。该谓词报告为
    ``warning``，不阻塞后续 pass。

    compat dialect 用 ``ENTER_SCOPE``/``EXIT_SCOPE``，abstract-machine dialect
    用 ``SS_ENTER``/``SS_LEAVE``；两者都检查。
    """
    out: list[Diagnostic] = []
    out.extend(
        _nesting_cfg(
            func, push="ENTER_SCOPE", pop="EXIT_SCOPE", label="ENTER_SCOPE", severity="warning"
        )
    )
    out.extend(
        _nesting_cfg(func, push="SS_ENTER", pop="SS_LEAVE", label="SS_ENTER", severity="warning")
    )
    return tuple(out)


# ─── L11 ─────────────────────────────────────────────────────────────────────
# "HANDLER_PUSH/HANDLER_POP 正确嵌套"


_HANDLER_OPCODES = ("HANDLER_PUSH", "HANDLER_POP")

# LIR terminators: an instruction after one of these is only reachable if it
# is a block entry point (jump / handler / continuation target).
_LIR_TERMINATORS = frozenset(
    {"RETURN", "TAIL_CALL", "RAISE_EFFECT", "CONT_RESTORE", "EFFECT_UNWIND"}
)


def _cfg_successors(func: LIRFunction, idx: int) -> list[int]:
    """Return the intra-function successors of instruction *idx*."""
    instructions = func.instructions
    count = len(instructions)
    inst = instructions[idx]
    opcode = inst.opcode
    out: list[int] = []
    if opcode == "JUMP":
        target = inst.operands[-1] if inst.operands else None
        if isinstance(target, int) and 0 <= target < count:
            out.append(target)
        return out
    if opcode in ("JUMP_IF_FALSE", "BRANCH_NIL"):
        if idx + 1 < count:
            out.append(idx + 1)
        target = inst.operands[-1] if inst.operands else None
        if isinstance(target, int) and 0 <= target < count:
            out.append(target)
        return out
    if opcode in _LIR_TERMINATORS:
        # EFFECT_UNWIND transfers into a handler dispatch block; that block's
        # handler depth is seeded from the matching HANDLER_PUSH instead.
        return out
    if idx + 1 < count:
        out.append(idx + 1)
    return out


def _relax_depth(depth_at: dict[int, int], work: list[int], node: int, depth: int) -> None:
    """Dataflow helper: record *depth* at *node* if not seen yet.

    Conflicting depths at a join point are left as first-seen: the point of
    this analysis is to catch push/pop underflow on reachable paths, not to
    prove stack-depth uniformity (a later pass owns that).
    """
    if node not in depth_at:
        depth_at[node] = depth
        work.append(node)


def _nesting_cfg(
    func: LIRFunction, *, push: str, pop: str, label: str, severity: Severity = "error"
) -> tuple[Diagnostic, ...]:
    """CFG-aware push/pop nesting check.

    A flat linear scan cannot see that a handler dispatch block is entered
    with the handler frame already pushed, nor that a continuation resume
    target is a block entry. Tracking depth over the CFG (with handler
    targets seeded by their ``HANDLER_PUSH``) removes those false positives
    while still reporting genuine underflow and unclosed frames.
    """
    instructions = func.instructions
    count = len(instructions)
    if count == 0:
        return ()

    out: list[Diagnostic] = []
    depth_at: dict[int, int] = {0: 0}
    work: list[int] = [0]
    reported: set[int] = set()

    while work:
        idx = work.pop()
        depth = depth_at[idx]
        inst = instructions[idx]
        next_depth = depth
        if inst.opcode == push:
            next_depth = depth + 1
            target = inst.operands[1] if len(inst.operands) >= 2 else None
            if isinstance(target, int) and 0 <= target < count:
                _relax_depth(depth_at, work, target, depth + 1)
        elif inst.opcode == pop:
            if depth < 1:
                if idx not in reported:
                    reported.add(idx)
                    out.append(
                        Diagnostic(
                            f"LIR function {func.name.name} {pop} at {idx} with no matching {push}",
                            severity=severity,
                        )
                    )
                next_depth = depth
            else:
                next_depth = depth - 1
        for successor in _cfg_successors(func, idx):
            _relax_depth(depth_at, work, successor, next_depth)

    for idx, inst in enumerate(instructions):
        if inst.opcode in ("RETURN", "TAIL_CALL"):
            depth = depth_at.get(idx)
            if depth is not None and depth > 0:
                out.append(
                    Diagnostic(
                        f"LIR function {func.name.name} reaches {inst.opcode} at {idx} "
                        f"with {depth} unclosed {label}",
                        severity=severity,
                    )
                )
                break
    return tuple(out)


def l11_handler_push_pop_nesting(func: LIRFunction) -> tuple[Diagnostic, ...]:
    return _nesting_cfg(func, push="HANDLER_PUSH", pop="HANDLER_POP", label="HANDLER_PUSH")


# ─── L12 ─────────────────────────────────────────────────────────────────────
# "FRAME_ENTER/FRAME_LEAVE 正确嵌套"


_FRAME_OPCODES = ("FRAME_ENTER", "FRAME_LEAVE")


def l12_frame_enter_leave_nesting(func: LIRFunction) -> tuple[Diagnostic, ...]:
    return _nesting_cfg(func, push="FRAME_ENTER", pop="FRAME_LEAVE", label="FRAME_ENTER")


# ─── L14 ─────────────────────────────────────────────────────────────────────
# "compat dialect 不得包含 abstract-machine-only opcodes"


_ABSTRACT_MACHINE_ONLY_OPCODES = frozenset(
    {
        "FRAME_ENTER",
        "FRAME_LEAVE",
        "SS_ENTER",
        "SS_LEAVE",
        "SS_COPY",
        "SS_RESTORE",
        "SS_LOOKUP",
        "SLOT_READ",
        "SLOT_COMPLETE",
        "SLOT_PENDING_EFFORT",
        "CONT_CAPTURE",
        "CONT_COPY",
        "CONT_RESTORE",
        "CONT_INJECT",
        "HANDLER_PUSH",
        "HANDLER_POP",
        "EFFECT_UNWIND",
        "EFFECT_DISPATCH",
    }
)


def l14_compat_no_abstract_machine_opcodes(program: LIRProgram) -> tuple[Diagnostic, ...]:
    if program.dialect != "compat":
        return ()
    out: list[Diagnostic] = []
    for func in program.functions:
        for idx, inst in enumerate(func.instructions):
            if inst.opcode in _ABSTRACT_MACHINE_ONLY_OPCODES:
                out.append(
                    Diagnostic(
                        f"LIR function {func.name.name} at {idx} uses "
                        f"abstract-machine-only opcode {inst.opcode!r} in "
                        "compat dialect"
                    )
                )
    return tuple(out)


# ─── Program entry ───────────────────────────────────────────────────────────


def check_program(program: LIRProgram) -> tuple[Diagnostic, ...]:
    """对整个 LIR program 运行 Phase 1 新增 / future-proof 谓词。.

    既有 L1, L3 partial, L4, L13, L15, def-use 等仍由 :func:`verify_lir` 在
    :mod:`qy.ir.lir.verify` 中实施；本入口运行 L2, L5..L12, L14。
    """
    out: list[Diagnostic] = []
    out.extend(l2_unique_function_ids(program))
    for func in program.functions:
        out.extend(l5_frame_layout_consistent(func))
        out.extend(l6_continuation_layout_consistent(func))
        out.extend(l10_scope_nesting(func))
        out.extend(l11_handler_push_pop_nesting(func))
        out.extend(l12_frame_enter_leave_nesting(func))
    out.extend(l7_handler_parent_exists(program))
    out.extend(l8_slot_address_in_space(program))
    out.extend(l9_slot_complete_at_most_once(program))
    out.extend(l14_compat_no_abstract_machine_opcodes(program))
    return tuple(out)
