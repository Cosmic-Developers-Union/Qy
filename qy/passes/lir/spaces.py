# coding: utf-8
"""LIR symbol-space / binding-slot assignment (abstract-machine dialect).

把 LIR 里扁平的作用域与绑定操作显式化为 Qy 抽象机的 symbol-space layout：

- ``ENTER_SCOPE`` -> ``SS_ENTER(space_id)``（进入一个新的 symbol space）
- ``EXIT_SCOPE``  -> ``SS_LEAVE(space_id)``
- ``DEFINE_ONCE`` -> ``SLOT_COMPLETE(address, src_reg)``，其中
  ``address = LIRBindingAddr(space_id, slot_index)``

并在 ``LIRFunction.symbol_spaces`` 上产出 ``LIRSymbolSpaceLayout``。这样
L8（slot address 必须指向存在的 space）与 L9（同一 slot 至多 complete 一次）
才真正有数据可校验。

职责边界：symbol-space-chain transition、lookup、slot operation 的**低层
layout** 属于 LIR（见 ``docs/ir-design.md`` §4.3）。HIR 层的符号提升 /
binding slot 分配（``passes/resolve/spaces.py``）仍是独立待办。

当前：本 pass 只在 ``lir_dialect == "abstract-machine"`` 时运行。它按线性
指令流维护 scope 栈，因此要求 ``ENTER_SCOPE`` / ``EXIT_SCOPE`` 在
linearize 之后仍是词法嵌套的（L10 负责校验这一点）。
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.core.syntax import Symbol
from qy.ir.lir import LIRBindingAddr
from qy.ir.lir import LIRBindingSlot
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRSymbolSpaceLayout

__all__ = ["assign_symbol_spaces"]


@dataclass(slots=True)
class _SpaceResult:
    instructions: list[LIRInstruction]
    symbol_spaces: tuple[LIRSymbolSpaceLayout, ...]


@dataclass(slots=True)
class _SpaceBuilder:
    id: int
    name: str
    parent: int | None
    slots: list[LIRBindingSlot]
    slot_index: dict[Symbol, int]


def assign_symbol_spaces(instructions: list[LIRInstruction], *, function_name: str) -> _SpaceResult:
    """Rewrite scope/define ops and build the symbol-space layout."""
    root = _SpaceBuilder(
        id=0,
        name=f"{function_name}:root",
        parent=None,
        slots=[],
        slot_index={},
    )
    spaces: dict[int, _SpaceBuilder] = {0: root}
    scope_stack: list[int] = [0]
    next_space_id = 1

    rewritten: list[LIRInstruction] = []
    for inst in instructions:
        opcode = inst.opcode
        if opcode in ("ENTER_SCOPE", "SS_ENTER"):
            parent = scope_stack[-1]
            space_id = next_space_id
            next_space_id += 1
            spaces[space_id] = _SpaceBuilder(
                id=space_id,
                name=f"{function_name}:scope{space_id}",
                parent=parent,
                slots=[],
                slot_index={},
            )
            scope_stack.append(space_id)
            rewritten.append(LIRInstruction("SS_ENTER", (space_id,), inst.span))
            continue
        if opcode in ("EXIT_SCOPE", "SS_LEAVE"):
            space_id = scope_stack.pop() if len(scope_stack) > 1 else 0
            rewritten.append(LIRInstruction("SS_LEAVE", (space_id,), inst.span))
            continue
        if opcode == "DEFINE_ONCE" and len(inst.operands) >= 2:
            symbol = inst.operands[0]
            source = inst.operands[1]
            if isinstance(symbol, Symbol):
                space = spaces[scope_stack[-1]]
                slot = space.slot_index.get(symbol)
                if slot is None:
                    slot = len(space.slots)
                    space.slot_index[symbol] = slot
                    space.slots.append(
                        LIRBindingSlot(
                            address=LIRBindingAddr(space.id, slot),
                            symbol=symbol,
                            state="completed",
                        )
                    )
                rewritten.append(
                    LIRInstruction(
                        "SLOT_COMPLETE",
                        (LIRBindingAddr(space.id, slot), source),
                        inst.span,
                    )
                )
                continue
        rewritten.append(inst)

    layouts = tuple(
        LIRSymbolSpaceLayout(
            id=space.id,
            name=space.name,
            parent=space.parent,
            slots=tuple(space.slots),
        )
        for space in spaces.values()
    )
    return _SpaceResult(rewritten, layouts)
