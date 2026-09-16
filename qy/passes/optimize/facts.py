# coding: utf-8
"""optimize pass 共享的 MIR 事实与重建工具。.

- :func:`shadowed_names`：程序内被显式绑定或导入的名字集合。任何"把
  ``LOAD_ENV symbol`` 当作已知内置算子 / 字面量"的优化都必须先排除这些名字，
  因为 ``define`` / ``let`` / ``from`` 都可以 shadow 它们。
- :func:`rebuild_program`：只替换 ``functions`` / ``constants``，保留
  ``symbol_spaces`` 等其余事实，避免优化 pass 静默丢掉 layout。

禁止：
- 不得在这里做语义判断（判定属于各 pass 自己）；
- 不得丢弃 ``MIRProgram.symbol_spaces``。
"""

from __future__ import annotations

from dataclasses import replace

from qy.core.syntax import Symbol
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRProgram

__all__ = ["rebuild_program", "shadowed_names"]


def shadowed_names(program: MIRProgram) -> frozenset[str]:
    """程序内被显式绑定（``define`` / ``let``）或 ``from`` 导入的名字。."""
    names: set[str] = set()
    for function in program.functions:
        for block in function.blocks:
            for inst in block.instructions:
                if inst.opcode in ("DEFINE_ONCE", "STORE_LOCAL") and inst.operands:
                    symbol = inst.operands[0]
                    if isinstance(symbol, Symbol):
                        names.add(symbol.name)
                elif inst.opcode == "FROM_IMPORT" and len(inst.operands) >= 2:
                    specs = inst.operands[1]
                    if isinstance(specs, tuple):
                        for spec in specs:
                            alias = getattr(spec, "alias", None)
                            if isinstance(alias, Symbol):
                                names.add(alias.name)
    return frozenset(names)


def rebuild_program(
    program: MIRProgram,
    *,
    functions: tuple[MIRFunction, ...] | None = None,
    constants: MIRConstantPool | None = None,
) -> MIRProgram:
    """Rebuild *program* preserving every fact except the replaced fields."""
    updates: dict[str, object] = {}
    if functions is not None:
        updates["functions"] = functions
    if constants is not None:
        updates["constants"] = constants
    return replace(program, **updates)
