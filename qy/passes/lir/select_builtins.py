# coding: utf-8
"""lir.select_builtins pass。.

把**静态可解析**的内建算子调用从通用 `CALL` 降为 `CALL_BUILTIN`：

```text
LOAD_ENV r_op, Symbol("+")        LOAD_ENV r_op, Symbol("+")   ← 无剩余使用时删除
CALL dest, r_op, (a, b)      ->   CALL_BUILTIN dest, 0, (a, b)
```

这就是 LIR 的 "selection" 职责：决定用哪条 ABI，而不是重新解释语义。语义实现仍
单源在 `qy.std` / `qy.session`（VM 侧 `qy/vm/instance/builtins.py` 直接取用同一批
实现），bytecode 只携带内建下标，wasm / llvm 后端消费同一个下标表
（`qy/core/operator_builtins.py`）。

选中条件（全部满足才改写）：

1. 被调用寄存器在本函数内**唯一**由 ``LOAD_ENV`` 定义（跨块"最后一次写"不支配使用点）；
2. 该 symbol 是内建算子，且实参个数等于它的 ABI 元数；
3. 该 symbol 在**本程序内未被** ``DEFINE_ONCE`` / ``STORE_LOCAL`` / ``from`` 导入
   绑定（shadow 后运行期不再是内建算子）；
3b. 解析结果是**纯算子**（``PureOperator``）：效果/作用域算子的调用约定需要 env，
   由通用 ``CALL`` 路径处理；
4. **会话 env** 解析该 symbol 得到的就是标准实现对象（宿主可以注入同名覆盖，
   例如把 ``+`` 换成自己的函数；此时不得改成内建调用）。

禁止：
- 不得在这里重新实现算子语义（语义在 `qy.std` / `qy.session`）；
- 不得改写 ``CALL`` 之外的形式（``TAIL_CALL`` 的 selection 另做）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from qy.core.operator_builtins import BUILTIN_INDEX
from qy.core.operator_builtins import BUILTIN_OPERATORS
from qy.core.syntax import Symbol
from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRProgram
from qy.ir.lir import register_operands_of
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["SelectBuiltinCallsPass"]


class SelectBuiltinCallsPass(Pass):
    def __init__(self):
        super().__init__("lir.select_builtins")

    def run(self, context: PassContext) -> PassResult:
        program = cast(LIRProgram, context.input_artifact)
        session_env = context.session.env
        canonical = _canonical_operators(session_env)

        shadowed = _shadowed_names(program)
        new_functions = tuple(
            _select_in_function(function, shadowed, canonical) for function in program.functions
        )
        if new_functions == program.functions:
            return PassResult(success=True, artifact=program)

        return PassResult(
            success=True,
            artifact=replace(program, functions=new_functions),
        )


def _canonical_operators(session_env: object) -> dict[str, object]:
    """会话 env 里确实解析到**语言实现自身**的内建算子名 -> 算子对象。.

    宿主可以向实例 env 注入同名绑定（例如用自己的 ``+``）或让它指向 Qy 函数；
    只有解析结果仍是语言实现算子时才允许降成内建调用，否则走通用路径。
    """
    from qy.core.operator_builtins import is_language_implementation_operator
    from qy.core.operators import PureOperator
    from qy.core.syntax import Symbol as QySymbol
    from qy.session.runtime_space import RuntimeSpace

    if not isinstance(session_env, RuntimeSpace):
        return {}
    result: dict[str, object] = {}
    for operator in BUILTIN_OPERATORS:
        try:
            resolved = session_env.resolve(QySymbol(operator.name))
        except Exception:
            continue
        if not isinstance(resolved, PureOperator):
            # 效果/作用域算子的调用约定需要 env；CALL_BUILTIN 只承载纯算子快路径。
            continue
        if is_language_implementation_operator(resolved):
            result[operator.name] = resolved
    return result


def _shadowed_names(program: LIRProgram) -> frozenset[str]:
    """程序内被显式绑定或 ``from`` 导入的名字（与 optimize.facts 同一规则）。."""
    names: set[str] = set()
    for function in program.functions:
        for inst in function.instructions:
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


def _select_in_function(
    function: LIRFunction,
    shadowed: frozenset[str],
    canonical: dict[str, object],
) -> LIRFunction:
    if not canonical:
        return function

    instructions = function.instructions
    jump_targets = _jump_targets(instructions)

    # 对每个 CALL：找到它之前**最近一次写 callee 寄存器**的指令；只有当那次写是
    # 内建算子的 LOAD_ENV，且 LOAD_ENV 与该 CALL 之间没有跳转目标（没有别的路径
    # 从中间进入、带着另一个值）时，才静态确定 callee。
    rewritten: list[LIRInstruction] = []
    selected_registers: set[int] = set()
    for index, inst in enumerate(instructions):
        if inst.opcode != "CALL" or len(inst.operands) < 3:
            rewritten.append(inst)
            continue
        dest, callee_reg, arg_regs = inst.operands
        if not isinstance(callee_reg, int) or not isinstance(arg_regs, tuple):
            rewritten.append(inst)
            continue
        definition_index = _nearest_write(instructions, index, callee_reg)
        if definition_index is None:
            rewritten.append(inst)
            continue
        definition = instructions[definition_index]
        symbol = (
            definition.operands[1]
            if definition.opcode == "LOAD_ENV" and len(definition.operands) >= 2
            else None
        )
        if not isinstance(symbol, Symbol):
            rewritten.append(inst)
            continue
        if any(target in range(definition_index + 1, index + 1) for target in jump_targets):
            rewritten.append(inst)
            continue
        builtin_id = BUILTIN_INDEX.get(symbol.name)
        if (
            builtin_id is None
            or symbol.name in shadowed
            or symbol.name not in canonical
            or len(arg_regs) != BUILTIN_OPERATORS[builtin_id].arity
        ):
            rewritten.append(inst)
            continue
        rewritten.append(LIRInstruction("CALL_BUILTIN", (dest, builtin_id, arg_regs), inst.span))
        selected_registers.add(callee_reg)

    if not selected_registers:
        return function

    # 统计剩余使用；只删除"改写后无人使用"的 LOAD_ENV（它仍会做一次 env 查找）
    candidate_definitions = set()
    for register in selected_registers:
        for index, inst in enumerate(instructions):
            if inst.opcode == "LOAD_ENV" and inst.operands and inst.operands[0] == register:
                candidate_definitions.add(index)

    used_registers: set[int] = set()
    for inst in rewritten:
        if inst.opcode == "CALL_BUILTIN":
            used_registers.update(
                item for item in cast(tuple, inst.operands[2]) if isinstance(item, int)
            )
            continue
        for operand in register_operands_of(inst.opcode, inst.operands):
            if isinstance(operand, int):
                used_registers.add(operand)

    final: list[LIRInstruction] = []
    for index, inst in enumerate(rewritten):
        if (
            index in candidate_definitions
            and isinstance(inst.operands[0], int)
            and inst.operands[0] not in used_registers
        ):
            continue
        final.append(inst)

    if tuple(final) == function.instructions:
        return function
    return replace(function, instructions=tuple(final))


def _jump_targets(instructions: tuple[LIRInstruction, ...]) -> set[int]:
    """线性指令流里的跳转目标下标（含 effect resume 目标）。."""
    targets: set[int] = set()
    for inst in instructions:
        operands = inst.operands
        if not operands:
            continue
        if inst.opcode in ("JUMP", "JUMP_IF_FALSE", "BRANCH_NIL"):
            target = operands[-1]
        elif inst.opcode == "EFFECT_PERFORM" and len(operands) >= 4:
            target = operands[3]
        else:
            continue
        if isinstance(target, int):
            targets.add(target)
    return targets


def _nearest_write(
    instructions: tuple[LIRInstruction, ...], index: int, register: int
) -> int | None:
    """返回 index 之前最近一次写 *register* 的指令下标。."""
    for candidate in range(index - 1, -1, -1):
        inst = instructions[candidate]
        if not inst.operands:
            continue
        dest = inst.operands[0]
        if isinstance(dest, int) and dest == register:
            return candidate
    return None
