# coding: utf-8
"""optimize.const_prop pass.

把「字面量拼写的 env lookup」降成常量加载：

- ``LOAD_ENV dest, Symbol("42")`` -> ``LOAD_CONST dest, <IntValue(42)>``
- 同样适用于字符串 / 字符 / ``T`` / ``nil`` / ``none`` 拼写。

MIR 里 bare literal 是以 symbol 拼写形式存在的（``LOAD_ENV`` 走运行时
literal resolver），因此这一步把每次求值都发生的 symbol-space 查找换成
常量池读取。

正确性约束：

- 只有当该拼写在**整个程序**内没有被任何 ``DEFINE_ONCE`` / ``STORE_LOCAL``
  绑定（``define`` 允许 shadow 字面量拼写）且没有被 ``from`` 导入同名绑定
  （``ImportSpec.alias``）时才改写；
- 还必须核对**真实运行时 env**：宿主可以向实例 env 注入任意绑定（包括字面量拼写），
  因此要求 ``env.resolve(symbol) == 默认字面量``；字符串 / 字符的 identity 目前是
  可观察的（``=`` 按 identity 比较），一律不改写；
- 只改写 literal resolver 能解析的拼写（``default_literal_type`` 非 None）；
- 不改写 CALL / BUILD_TUPLE 的操作数：MIR 用虚拟寄存器传参，把寄存器号换成
  常量池下标会读错寄存器（历史缺陷，见本条修复）。

禁止：
- 不得改写带副作用的符号查找（算子、effect）；
- 不得臆造寄存器：本 pass 不新增指令，也不改变 ``register_count``。
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from qy.core.symbol_space import MISSING
from qy.core.syntax import Symbol
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRConstantPool
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.passes.optimize.facts import rebuild_program
from qy.passes.optimize.facts import shadowed_names
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.session.pre_ss import default_literal_type
from qy.session.pre_ss import try_default_literal

__all__ = ["ConstPropagationPass"]


class ConstPropagationPass(Pass):
    def __init__(self):
        super().__init__("optimize.const_prop")

    def run(self, context: PassContext) -> PassResult:
        program = cast(MIRProgram, context.input_artifact)
        pool = MIRConstantPool()
        for value in program.constants.values:
            pool.intern(value)

        shadowed = shadowed_names(program)
        env = context.session.env
        new_functions = tuple(
            _rewrite_function(function, pool, shadowed, env) for function in program.functions
        )
        return PassResult(
            success=True,
            artifact=rebuild_program(program, functions=new_functions, constants=pool),
        )


def _rewrite_function(
    function: MIRFunction,
    pool: MIRConstantPool,
    shadowed: frozenset[str],
    env: object | None,
) -> MIRFunction:
    blocks = tuple(
        MIRBlock(
            block.id,
            tuple(_rewrite_instruction(inst, pool, shadowed, env) for inst in block.instructions),
            block.terminator,
        )
        for block in function.blocks
    )
    return replace(function, blocks=blocks)


#: 只有这些字面量类别的 identity 不可观察，才可以安全地替换成常量。
#: - number：``=`` 按值比较；
#: - nil / T / none：自身对象单例。
#: string / char 被排除：``(= "abc" "abc")`` 目前为 ``nil``（按 identity 比较）。
_SAFE_LITERAL_KINDS = frozenset({"number", "nil", "T", "none"})


def _rewrite_instruction(
    instruction: MIRInstruction,
    pool: MIRConstantPool,
    shadowed: frozenset[str],
    env: object | None,
) -> MIRInstruction:
    if instruction.opcode != "LOAD_ENV" or len(instruction.operands) < 2:
        return instruction
    dest, symbol = instruction.operands[0], instruction.operands[1]
    if not isinstance(dest, int) or not isinstance(symbol, Symbol):
        return instruction
    kind = default_literal_type(symbol)
    if symbol.name in shadowed or kind not in _SAFE_LITERAL_KINDS:
        return instruction
    value = try_default_literal(symbol)
    if value is MISSING:
        return instruction
    if not _env_agrees(env, symbol, value):
        return instruction
    return MIRInstruction("LOAD_CONST", (dest, pool.intern(value)), instruction.span)


def _env_agrees(env: object | None, symbol: Symbol, default: object) -> bool:
    """真实 env 必须把该拼写解析成同一个字面量值（宿主可以注入覆盖）。."""
    from qy.session.runtime_space import RuntimeSpace

    if not isinstance(env, RuntimeSpace):
        return False
    try:
        resolved = env.resolve(symbol)
    except Exception:
        return False
    return bool(resolved == default)
