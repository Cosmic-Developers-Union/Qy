# coding: utf-8
"""LIR symbol-space / binding-slot assignment (abstract-machine dialect).

把 LIR 里扁平的作用域与绑定操作显式化为 Qy 抽象机的 symbol-space layout：

- ``ENTER_SCOPE(space_id)`` -> ``SS_ENTER(space_id)``
- ``EXIT_SCOPE(space_id)``  -> ``SS_LEAVE(space_id)``
- ``DEFINE_ONCE(symbol, src)`` -> ``SLOT_COMPLETE(address, src)``，其中
  ``address = LIRBindingAddr(space_id, slot_index)``；``slot_index`` 来自
  **program-level layout**（HIR ``resolve.spaces`` 产出、经 MIR 下沉的那一份），
  不是在这里重新分配。

单一事实源：layout 的 id / slot 只在 ``passes/resolve/spaces.py`` 分配一次；
MIR 的 ``ENTER_SCOPE`` 携带该 id，本模块只做「查表 + 指令改写」。当当前 space
没有 program-level layout（``space_id == -1``）或该 symbol 在该 space 里没有 slot
时，``DEFINE_ONCE`` 原样保留（两个 dialect 都允许该指令），不臆造地址。

当前：本 pass 只在 ``lir_dialect == "abstract-machine"`` 时运行。
"""

from __future__ import annotations

from qy.core.syntax import Symbol
from qy.ir.layout import BindingSlot
from qy.ir.layout import SymbolSpaceLayout
from qy.ir.lir import LIRBindingAddr
from qy.ir.lir import LIRInstruction

__all__ = ["assign_symbol_spaces"]


def _slot_index(layout: SymbolSpaceLayout | None, symbol: object) -> int | None:
    if layout is None or not isinstance(symbol, Symbol):
        return None
    for slot in layout.slots:
        if isinstance(slot, BindingSlot) and slot.symbol == symbol:
            return slot.index
    return None


def assign_symbol_spaces(
    instructions: list[LIRInstruction],
    *,
    program_layout: tuple[SymbolSpaceLayout, ...],
    function_space_id: int = -1,
) -> list[LIRInstruction]:
    """Rewrite scope/define ops using the *program-level* symbol-space layout.

    ``function_space_id`` 是该函数体所属的 lexical space（lambda/defun/module
    的 body space，或 <main> 的 root space）；它作为 scope 栈的初始值，使函数体
    顶层的 ``DEFINE_ONCE`` 也能解析到 slot。
    """
    layouts = {layout.id: layout for layout in program_layout}
    scope_stack: list[int] = [] if function_space_id < 0 else [function_space_id]
    rewritten: list[LIRInstruction] = []

    for inst in instructions:
        opcode = inst.opcode
        if opcode in ("ENTER_SCOPE", "SS_ENTER"):
            space_id = inst.operands[0] if inst.operands else -1
            scope_stack.append(space_id if isinstance(space_id, int) else -1)
            rewritten.append(LIRInstruction("SS_ENTER", (scope_stack[-1],), inst.span))
            continue
        if opcode in ("EXIT_SCOPE", "SS_LEAVE"):
            space_id = scope_stack.pop() if scope_stack else -1
            rewritten.append(LIRInstruction("SS_LEAVE", (space_id,), inst.span))
            continue
        if opcode == "DEFINE_ONCE" and len(inst.operands) >= 2:
            symbol, source = inst.operands[0], inst.operands[1]
            space_id = scope_stack[-1] if scope_stack else -1
            slot = _slot_index(layouts.get(space_id), symbol)
            if slot is not None:
                rewritten.append(
                    LIRInstruction(
                        "SLOT_COMPLETE",
                        (LIRBindingAddr(space_id, slot), source),
                        inst.span,
                    )
                )
                continue
        rewritten.append(inst)

    return rewritten
