# coding: utf-8
"""optimize 内联 pass 的共享内核。.

``optimize.inline`` 与 ``optimize.aggressive_inline`` 的**唯一事实源**：健全性
判定、调用点发现、把 callee 搬进 caller 寄存器空间的实际改写，全部在这里。
两个 pass 只保留各自的策略（单调用点 / 多调用点 + 指令预算 + 深度）。

健全性条件（MIR 层没有作用域对象，因此必须用程序级事实判定）：

- 不得含 effect / 动态求值 / 空间副作用（``DEFINE_ONCE`` / ``STORE_LOCAL`` /
  ``ENTER_SCOPE`` …）：内联会把这些效果搬到调用者的 symbol-space；
- 不得含嵌套 ``MAKE_FUNCTION``：内联后内层闭包会捕获调用者的 env；
- 形参在 MIR 中是通过 ``LOAD_ENV`` 读名字的（VM 把实参按名字绑进子 env），
  内联时必须把**形参的 ``LOAD_ENV`` 替换成从实参寄存器 ``MOVE``**，否则会读到
  调用者 env 里的同名绑定；
- 其余 ``LOAD_ENV`` 的名字不得是程序内任何 symbol-space 的绑定（闭包变量），
  否则内联后解析到调用者 env（历史缺陷：``unresolved symbol 'f'``）；只有未在
  layout 中出现的名字（profile 算子 / 字面量）才可以跨 env 解析。

寄存器位移一律走 ``qy.ir.mir`` 的寄存器操作数表，不得自行猜测哪些操作数是寄存器。

禁止：不得在这里放策略（预算 / 深度 / 调用点数量由各 pass 决定）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from qy.core.syntax import Symbol
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.ir.mir import register_operand_positions
from qy.ir.mir import register_tuple_positions

__all__ = [
    "count_calls",
    "drop_functions",
    "find_all_call_sites",
    "find_call_site",
    "inline_into",
    "is_inlinable",
    "is_recursive",
    "lexical_names",
    "remap_fn_indices",
]

#: MIR 里真正的 effect 相关 opcode（历史实现写的是 ``HANDLE`` / ``PERFORM`` 等
#: 从未存在的名字，守卫实际是死代码）。
EFFECT_OPCODES = frozenset(
    {
        "EFFECT_HANDLE_BEGIN",
        "EFFECT_HANDLE_END",
        "EFFECT_PERFORM",
        "EFFECT_RESUME",
        "RAISE_EFFECT",
    }
)
#: 会改变 symbol-space / 捕获 env / 依赖运行期解析的 opcode：一律不内联。
SIDE_EFFECT_OPCODES = frozenset(
    {
        "DEFINE_ONCE",
        "STORE_LOCAL",
        "DEFINE_MODULE",
        "FROM_IMPORT",
        "DEFEFFECT",
        "ENTER_SCOPE",
        "EXIT_SCOPE",
        "MAKE_FUNCTION",
        "MAKE_MACRO",
        "CACHE_EVAL",
        "RUNTIME_EVAL",
    }
)
ALLOWED_TERMINATORS = frozenset({"JUMP", "BRANCH", "RETURN"})


def lexical_names(program: MIRProgram) -> frozenset[str]:
    """程序内所有 symbol-space 的绑定名（来自 P1-1 的 layout 单一事实源）。."""
    names: set[str] = set()
    for layout in program.symbol_spaces:
        for slot in layout.slots:
            names.add(slot.symbol.name)
    return frozenset(names)


def is_inlinable(fn: MIRFunction, lexical: frozenset[str]) -> bool:
    """判定 fn 是否可以在 MIR 层安全内联（见模块 docstring 的健全性条件）。."""
    params = {param.name for param in fn.params}
    for block in fn.blocks:
        for inst in block.instructions:
            if inst.opcode in EFFECT_OPCODES or inst.opcode in SIDE_EFFECT_OPCODES:
                return False
            if inst.opcode == "LOAD_ENV" and len(inst.operands) >= 2:
                symbol = inst.operands[1]
                if not isinstance(symbol, Symbol):
                    return False
                # 形参由替换处理；其他词法绑定（闭包变量）不能跨 env 解析。
                if symbol.name not in params and symbol.name in lexical:
                    return False
        if block.terminator.opcode not in ALLOWED_TERMINATORS:
            return False
    return True


def is_recursive(fn: MIRFunction, fn_idx: int) -> bool:
    for block in fn.blocks:
        for inst in block.instructions:
            if inst.opcode == "MAKE_FUNCTION" and inst.operands[1] == fn_idx:
                return True
    return False


def count_calls(functions: list[MIRFunction]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for fn in functions:
        for block in fn.blocks:
            for inst in block.instructions:
                if inst.opcode == "MAKE_FUNCTION":
                    fn_idx = inst.operands[1]
                    if isinstance(fn_idx, int):
                        counts[fn_idx] = counts.get(fn_idx, 0) + 1
    return counts


def find_call_site(functions: list[MIRFunction], target_fn_idx: int) -> tuple[int, int, int] | None:
    sites = find_all_call_sites(functions, target_fn_idx)
    return sites[0] if sites else None


def find_all_call_sites(
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
                    if _same_symbol(inst.operands[1], defined_symbol):
                        make_fn_reg = cast(int, inst.operands[0])

                if (
                    inst.opcode == "CALL"
                    and make_fn_reg is not None
                    and inst.operands[1] == make_fn_reg
                ):
                    sites.append((caller_idx, bi, ii))

    return sites


def _same_symbol(a: object, b: object) -> bool:
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    return a == b


def inline_into(
    caller: MIRFunction,
    call_block_idx: int,
    call_inst_idx: int,
    callee: MIRFunction,
    callee_fn_idx: int,
    *,
    max_instructions: int | None = None,
) -> MIRFunction | None:
    """把 callee 的唯一调用点展开进 caller；不满足前提时返回 None。."""
    if max_instructions is not None:
        total = sum(len(block.instructions) for block in callee.blocks)
        if total > max_instructions:
            return None

    call_block = caller.blocks[call_block_idx]
    call_inst = call_block.instructions[call_inst_idx]
    dest_reg, _op_reg, arg_regs = call_inst.operands

    if not isinstance(arg_regs, tuple):
        return None
    if len(arg_regs) != len(callee.params):
        return None

    reg_offset = caller.register_count
    max_block_id = max(b.id for b in caller.blocks) + 1

    # 形参 -> 实参寄存器：内联后的 body 直接从这些寄存器读值。
    param_values = {
        param.name: cast(int, arg_reg)
        for param, arg_reg in zip(callee.params, arg_regs, strict=True)
    }

    inlined_entry_id = max_block_id + callee.entry
    continuation_id = max_block_id + len(callee.blocks)

    pre_block = MIRBlock(
        call_block.id,
        tuple(
            inst
            for inst in call_block.instructions[:call_inst_idx]
            if inst.opcode != "MAKE_FUNCTION" or inst.operands[1] != callee_fn_idx
        ),
        MIRTerminator("JUMP", (inlined_entry_id,), call_inst.span),
    )

    continuation_block = MIRBlock(
        continuation_id,
        call_block.instructions[call_inst_idx + 1 :],
        call_block.terminator,
    )

    inlined_blocks: list[MIRBlock] = []
    for block in callee.blocks:
        new_instructions = list(
            _offset_instruction(inst, reg_offset, param_values) for inst in block.instructions
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
        inlined_blocks.append(
            MIRBlock(max_block_id + block.id, tuple(new_instructions), new_terminator)
        )

    new_blocks = list(caller.blocks)
    new_blocks[call_block_idx] = pre_block
    new_blocks.append(continuation_block)
    new_blocks.extend(inlined_blocks)

    # 内联后的代码属于 caller 的 symbol-space（callee 的空间副作用已在
    # is_inlinable 中排除），因此继承 caller 的 space_id。
    return replace(
        caller,
        register_count=caller.register_count + callee.register_count,
        blocks=tuple(new_blocks),
    )


def _offset_instruction(
    inst: MIRInstruction,
    reg_offset: int,
    param_values: dict[str, int],
) -> MIRInstruction:
    """把 callee 指令搬进 caller 的寄存器空间。.

    - ``LOAD_ENV`` 读形参时替换为 ``MOVE dest, 实参寄存器``；
    - 其余寄存器操作数按 ``qy.ir.mir`` 的寄存器表整体偏移，非寄存器操作数
      （常量池下标 / 函数下标 / block id / space id）保持原值。
    """
    if inst.opcode == "LOAD_ENV" and len(inst.operands) >= 2:
        dest, symbol = inst.operands[0], inst.operands[1]
        if isinstance(symbol, Symbol) and symbol.name in param_values:
            return MIRInstruction(
                "MOVE", (cast(int, dest) + reg_offset, param_values[symbol.name]), inst.span
            )

    positions = register_operand_positions(inst)
    tuple_positions = register_tuple_positions(inst)
    operands = list(inst.operands)
    for index in positions:
        if index >= len(operands):
            continue
        operand = operands[index]
        if isinstance(operand, int):
            operands[index] = operand + reg_offset
    for index in tuple_positions:
        if index >= len(operands):
            continue
        value = operands[index]
        if isinstance(value, tuple):
            operands[index] = tuple(
                item + reg_offset if isinstance(item, int) else item for item in value
            )
    return MIRInstruction(inst.opcode, tuple(operands), inst.span)


def _offset_terminator(
    term: MIRTerminator,
    reg_offset: int,
    block_offset: int,
) -> MIRTerminator:
    match term.opcode:
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
        case _:
            return term


def remap_fn_indices(fn: MIRFunction, index_map: dict[int, int]) -> MIRFunction:
    """按 index_map 重写 ``MAKE_FUNCTION`` 的函数下标。."""
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
    return replace(fn, blocks=tuple(new_blocks))


def drop_functions(
    functions: list[MIRFunction],
    inlined_indices: set[int],
    main: int,
) -> tuple[list[MIRFunction], int]:
    """删除已内联的函数并重映射 ``MAKE_FUNCTION`` 下标。."""
    index_map: dict[int, int] = {}
    new_functions: list[MIRFunction] = []
    for old_idx, fn in enumerate(functions):
        if old_idx in inlined_indices:
            continue
        index_map[old_idx] = len(new_functions)
        new_functions.append(fn)

    new_functions = [remap_fn_indices(f, index_map) for f in new_functions]
    return new_functions, index_map.get(main, 0)
