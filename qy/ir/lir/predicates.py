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
    """同一 slot 不得被 ``SLOT_COMPLETE`` 多次执行（静态扫描指令流）。."""
    out: list[Diagnostic] = []
    completed: set[tuple[int, int]] = set()  # (space_id, slot_index)
    # 第一遍：收集 layout 声明的所有 slot
    declared: set[tuple[int, int]] = set()
    for func in program.functions:
        for space in getattr(func, "symbol_spaces", ()):
            for idx, _slot in enumerate(space.slots):
                declared.add((space.id, idx))

    # 第二遍：扫描 SLOT_COMPLETE 指令
    for func in program.functions:
        for inst in func.instructions:
            if inst.opcode != "SLOT_COMPLETE" or len(inst.operands) < 2:
                continue
            space_id, slot_idx = inst.operands[0], inst.operands[1]
            key: tuple[int, int] | None = None
            if isinstance(space_id, int) and isinstance(slot_idx, int):
                key = (space_id, slot_idx)
            if key is None:
                continue
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
    """
    out: list[Diagnostic] = []
    depth = 0
    for idx, inst in enumerate(func.instructions):
        if inst.opcode == "ENTER_SCOPE":
            depth += 1
        elif inst.opcode == "EXIT_SCOPE":
            depth -= 1
            if depth < 0:
                out.append(
                    Diagnostic(
                        f"LIR function {func.name.name} EXIT_SCOPE at {idx} "
                        "with no matching ENTER_SCOPE",
                        severity="warning",
                    )
                )
                depth = 0
    if depth > 0:
        out.append(
            Diagnostic(
                f"LIR function {func.name.name} has unclosed ENTER_SCOPE (depth={depth})",
                severity="warning",
            )
        )
    return tuple(out)


# ─── L11 ─────────────────────────────────────────────────────────────────────
# "HANDLER_PUSH/HANDLER_POP 正确嵌套"


_HANDLER_OPCODES = ("HANDLER_PUSH", "HANDLER_POP")


def l11_handler_push_pop_nesting(func: LIRFunction) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    depth = 0
    for idx, inst in enumerate(func.instructions):
        if inst.opcode == "HANDLER_PUSH":
            depth += 1
        elif inst.opcode == "HANDLER_POP":
            depth -= 1
            if depth < 0:
                out.append(
                    Diagnostic(
                        f"LIR function {func.name.name} HANDLER_POP at {idx} "
                        "with no matching HANDLER_PUSH"
                    )
                )
                depth = 0
    if depth > 0:
        out.append(
            Diagnostic(f"LIR function {func.name.name} has unclosed HANDLER_PUSH (depth={depth})")
        )
    return tuple(out)


# ─── L12 ─────────────────────────────────────────────────────────────────────
# "FRAME_ENTER/FRAME_LEAVE 正确嵌套"


_FRAME_OPCODES = ("FRAME_ENTER", "FRAME_LEAVE")


def l12_frame_enter_leave_nesting(func: LIRFunction) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    depth = 0
    for idx, inst in enumerate(func.instructions):
        if inst.opcode == "FRAME_ENTER":
            depth += 1
        elif inst.opcode == "FRAME_LEAVE":
            depth -= 1
            if depth < 0:
                out.append(
                    Diagnostic(
                        f"LIR function {func.name.name} FRAME_LEAVE at {idx} "
                        "with no matching FRAME_ENTER"
                    )
                )
                depth = 0
    if depth > 0:
        out.append(
            Diagnostic(f"LIR function {func.name.name} has unclosed FRAME_ENTER (depth={depth})")
        )
    return tuple(out)


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
