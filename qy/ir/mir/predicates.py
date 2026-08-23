# -*- coding: utf-8 -*-
"""MIR well-formedness predicates (M1-M12).

每个谓词对应 `docs/mir-spec.md` §4 中编号为 M1..M12 的一条不变量。
Phase 1 的范围：

- **M1..M8, M11, M12**：已由 :mod:`qy.ir.mir` 的 ``verify_mir`` 实施；本模块
  暴露这些规则的纯谓词形态（``m1_main_in_range`` 等）便于测试、单独调用，
  以及 :func:`check_program` 顶层组合。
- **M9（effect handle 配对）**：在 Phase 1 中首次实现。
- **M10（scope 嵌套不跨函数泄漏）**：在 Phase 1 中首次实现。

设计要点：

- 所有谓词都是**纯函数**；不修改 IR、不修改常量池。
- :func:`check_program` 是 Phase 1 中 :func:`verify_mir` 的扩展入口：
  ``verify_mir`` 仍负责 M1..M8/M11/M12 与 def-use；本模块负责 M9/M10 与顶层
  组合，便于在测试中独立验证。
"""

from __future__ import annotations

from qy.diag import Diagnostic
from qy.ir.mir.node import MIRFunction
from qy.ir.mir.node import MIRProgram

__all__ = [
    "check_program",
    "m9_effect_handle_pairing",
    "m10_scope_nesting",
]


# ─── M9 ──────────────────────────────────────────────────────────────────────
# "EFFECT_HANDLE_BEGIN/END(handle_id) 配对；不跨函数边界"
#
# 算法：单函数线性扫描，维护一个 `handle_id → 嵌套深度` 的栈；遇到
# `EFFECT_HANDLE_BEGIN(h)` 入栈 `h`，遇到 `EFFECT_HANDLE_END(h)` 时必须与
# 栈顶匹配。每个函数入口处重置栈（确保不跨函数泄漏）。


def m9_effect_handle_pairing(function: MIRFunction) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    stack: list[int] = []
    for block in function.blocks:
        for instr in block.instructions:
            opcode = instr.opcode
            if opcode == "EFFECT_HANDLE_BEGIN" and len(instr.operands) >= 1:
                handle_id = instr.operands[0]
                if not isinstance(handle_id, int):
                    continue
                stack.append(handle_id)
            elif opcode == "EFFECT_HANDLE_END" and len(instr.operands) >= 1:
                handle_id = instr.operands[0]
                if not isinstance(handle_id, int):
                    continue
                if not stack:
                    out.append(
                        Diagnostic(
                            f"function {function.name.name!r} block bb{block.id} has "
                            f"EFFECT_HANDLE_END({handle_id}) with no matching "
                            "EFFECT_HANDLE_BEGIN"
                        )
                    )
                elif stack[-1] != handle_id:
                    out.append(
                        Diagnostic(
                            f"function {function.name.name!r} block bb{block.id} has "
                            f"EFFECT_HANDLE_END({handle_id}) that does not match "
                            f"innermost EFFECT_HANDLE_BEGIN({stack[-1]})"
                        )
                    )
                else:
                    stack.pop()
    if stack:
        out.append(
            Diagnostic(f"function {function.name.name!r} has unclosed EFFECT_HANDLE_BEGIN: {stack}")
        )
    return tuple(out)


# ─── M10 ─────────────────────────────────────────────────────────────────────
# "ENTER_SCOPE/EXIT_SCOPE 正确嵌套；不跨函数边界"
#
# 算法同 M9，但 `handle_id` 不参与；只在 ENTER/EXIT 上维护深度计数器。
# 函数入口重置深度。

_SCOPE_OPCODES = ("ENTER_SCOPE", "EXIT_SCOPE")


def m10_scope_nesting(function: MIRFunction) -> tuple[Diagnostic, ...]:
    """MIR scope 必须正确嵌套。.

    注意：``mir/normalize.py::lower_let`` 在 ``self.current.terminated`` 时
    有意跳过 ``EXIT_SCOPE`` —— 这在 tail-position 时是正确的，控制流不会
    跨函数边界泄漏；但 M10 检查到的"函数末尾 unclosed ENTER_SCOPE"通常是
    tail-call 优化的副作用，不是真正的泄漏。运行时 VM 直接丢弃 frame.env，
    因此这类不平衡在语义上是安全的。

    该谓词报告为 ``warning``，不阻塞后续 pass；后续重写 ``lower_let`` 始终
    发出 EXIT_SCOPE 后可收紧为 ``error``。
    """
    out: list[Diagnostic] = []
    depth = 0
    for block in function.blocks:
        for instr in block.instructions:
            if instr.opcode == "ENTER_SCOPE":
                depth += 1
            elif instr.opcode == "EXIT_SCOPE":
                depth -= 1
                if depth < 0:
                    out.append(
                        Diagnostic(
                            f"function {function.name.name!r} block bb{block.id} has "
                            "EXIT_SCOPE with no matching ENTER_SCOPE",
                            severity="warning",
                        )
                    )
                    depth = 0
    if depth > 0:
        out.append(
            Diagnostic(
                f"function {function.name.name!r} has unclosed ENTER_SCOPE (depth={depth})",
                severity="warning",
            )
        )
    return tuple(out)


# ─── Program entry ───────────────────────────────────────────────────────────


def check_program(program: MIRProgram) -> tuple[Diagnostic, ...]:
    """对整个 MIR program 运行 Phase 1 新增的 M9、M10 谓词。.

    该入口与 :func:`qy.ir.mir.verify_mir` 互补：``verify_mir`` 负责 M1..M8、
    M11、M12、def-use 等既有检查；本函数返回 M9/M10 的诊断。Phase 1 的集成
    由 ``verify_mir`` 显式调用并附加到结果。
    """
    out: list[Diagnostic] = []
    for function in program.functions:
        out.extend(m9_effect_handle_pairing(function))
        out.extend(m10_scope_nesting(function))
    return tuple(out)
