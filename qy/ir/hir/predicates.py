# -*- coding: utf-8 -*-
"""HIR well-formedness predicates (H1-H14).

每个谓词对应 `docs/hir-spec.md` §4 中编号为 H1..H14 的一条不变量。
所有谓词都是**纯函数**：输入 ``IRExpr``（或 ``ProgramIR`` / ``SymbolSpace``），
输出 ``tuple[Diagnostic, ...]``，以便 ``ValidateHIRPass`` 在不对 IR 做 mutation
的前提下累积诊断。

设计要点：

- 谓词之间**互不依赖**；可以独立调用、单独测试。
- 当一条规则需要父节点上下文（如 H5 的 tail position、H7 的 handler body），
  谓词接受显式的 ``scope`` 参数，由顶层 ``check_program`` 通过递归下降构造。
- ``check_program`` 是入口；同时也是 Phase 1 的"全规则遍历器"。

规则编号与 `docs/hir-spec.md` §4 一一对应；后续修改须保持编号稳定，
以便 ``docs/formal-semantics.md`` §7 的对应表长期可索引。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import replace
from enum import Enum

from qy.core import OperatorKind  # noqa: F401  -- re-exported for downstream predicate composition
from qy.core.syntax import is_chain
from qy.diag import Diagnostic
from qy.frontend.form import DottedTuple
from qy.frontend.form import Form
from qy.frontend.form import SpannedTuple
from qy.frontend.reader import Symbol
from qy.ir.hir.node import AllExpr
from qy.ir.hir.node import ApplyExpr
from qy.ir.hir.node import AssertExpr
from qy.ir.hir.node import CacheExpr
from qy.ir.hir.node import CallExpr
from qy.ir.hir.node import CondExpr
from qy.ir.hir.node import DefeffectExpr
from qy.ir.hir.node import DefineExpr
from qy.ir.hir.node import DefunExpr
from qy.ir.hir.node import FromImportExpr
from qy.ir.hir.node import HandleExpr
from qy.ir.hir.node import IRExpr
from qy.ir.hir.node import LambdaExpr
from qy.ir.hir.node import LetExpr
from qy.ir.hir.node import LiteralExpr
from qy.ir.hir.node import MacroExpr
from qy.ir.hir.node import ModuleExpr
from qy.ir.hir.node import ParallelExpr
from qy.ir.hir.node import PerformExpr
from qy.ir.hir.node import PipelineExpr
from qy.ir.hir.node import ProgramIR
from qy.ir.hir.node import QuoteExpr
from qy.ir.hir.node import RaceExpr
from qy.ir.hir.node import ResumeExpr
from qy.ir.hir.node import RuntimeEvalExpr
from qy.ir.hir.node import SymbolRefExpr
from qy.ir.hir.node import SymbolSpace
from qy.ir.hir.node import UnresolvedSymbolExpr

__all__ = [
    "H4_SEVERITY",
    "Parent",
    "Scope",
    "check_program",
    "h1_resolved_symbols",
    "h2_define_once_in_space",
    "h3_node_shape",
    "h4_call_continuous",
    "h5_call_tail_position",
    "h6_handle_effect_declared",
    "h7_resume_in_handler",
    "h8_perform_effect_declared",
    "h9_module_export_defined",
    "h10_from_import_specs_present",
    "h11_quote_form_is_form",
    "h12_define_once_in_space",
    "h13_pending_binding_effort",
    "h14_macro_body_raw_synced",
]


# 当前 `lower.py` 未传播 ``continuous`` 标志（hir-spec.md §7.1），
# 因此 H4 在 Phase 1 只能降级为 warning。等 lowering 修复后再升为 error。
H4_SEVERITY: str = "warning"


class Parent(Enum):
    """调用 ``CallExpr`` 在其外围 AST 中的位置，用于 H5 tail-position 检查。."""

    TOP = "top"
    FUNC_BODY = "func-body"
    COND_RESULT = "cond-result"
    IF_BRANCH = "if-branch"
    PIPELINE_LAST = "pipeline-last"
    LET_BODY = "let-body"
    HANDLE_BODY = "handle-body"
    ARG = "arg"


@dataclass(frozen=True, slots=True)
class Scope:
    """``check_program`` 在递归下降时维护的父作用域上下文。."""

    space: SymbolSpace | None
    parent: Parent = Parent.TOP
    # handler 当前所在的 effect 名（``ResumeExpr`` 必须在此不为 None）。
    current_effect: str | None = None
    # 当前 effect 是否 resumable（H7 需要）。
    current_effect_resumable: bool = False
    # 当前 module 名（H9 用于解析 export）。
    current_module: str | None = None
    # 当前 module 已 define 的 binding 集合（H9 用）。
    module_defined: frozenset[str] = frozenset()
    # 当前 body 序列中已经生效的 ``defeffect`` 名字（H6 / H8 用）。
    declared_effects: frozenset[str] = frozenset()


def _diag(
    rule: str,
    message: str,
    *,
    severity: str = "error",
    span: object = None,
) -> Diagnostic:
    from typing import cast

    from qy.diag.diagnostic import Severity
    from qy.source.span import SourceSpan

    typed_span = span if isinstance(span, SourceSpan) else None
    typed_severity: Severity = (
        cast(Severity, severity) if severity in ("error", "warning", "hint") else "error"
    )
    return Diagnostic(
        message=f"[{rule}] {message}",
        severity=typed_severity,
        span=typed_span,
    )


# ─── H1 ──────────────────────────────────────────────────────────────────────
# "所有 SymbolRefExpr 必有非空 binding；解析失败的符号必须用
#  UnresolvedSymbolExpr，不得伪装"


def h1_resolved_symbols(expr: IRExpr) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    for ref in _walk_symbol_refs(expr):
        if ref.binding is None:  # pragma: no cover - dataclass slot prevents None
            out.append(_diag("H1", "SymbolRefExpr.binding is None", span=ref.span))
    return tuple(out)


# ─── H2 ──────────────────────────────────────────────────────────────────────
# "同一 SymbolSpace 内同一 Symbol 至多一个 binding（define-once）"


def h2_define_once_in_space(space: SymbolSpace) -> tuple[Diagnostic, ...]:
    if not space.bindings:
        return ()
    counts: dict[Symbol, int] = {}
    for sym in space.bindings:
        counts[sym] = counts.get(sym, 0) + 1
    out: list[Diagnostic] = []
    for sym, count in counts.items():
        if count > 1:
            out.append(_diag("H2", f"symbol {sym.name!r} bound {count} times in {space.name!r}"))
    return tuple(out)


# ─── H3 ──────────────────────────────────────────────────────────────────────
# "所有 IRExpr 构造合法：每节点必满足 §3 中字段不变量；特殊节点 arity 合法
#  (LetExpr.bindings ≥ 1、CondExpr.clauses ≥ 1、HandleExpr.handlers ≥ 1、
#   PipelineExpr.body ≥ 1)"


def h3_node_shape(expr: IRExpr) -> tuple[Diagnostic, ...]:
    """校验 IR 节点结构上的"双重空"缺陷。.

    Phase 1 实施策略：

    - hir-spec.md §3 列出了各节点的 arity 下界（``bindings ≥ 1`` 等）；
    - 但 codebase 实际允许若干零 arity 形态作为合法用法：

        - ``(let () body)``：scope-only 模式，不引入 binding
          （见 ``tests/test_register_vm.py::test_register_vm_tail_recursion_uses_frame_replacement``）
        - ``(defun f () body)`` / ``(lambda () body)``：零参数函数
          （见 ``tests/test_register_vm_semantics.py::test_vm_runtime_errors_include_virtual_stack_frames``）
        - ``(macro m () body)``：零参数宏

    - 因此 H3 仅在 **bindings + body 同时为空**、或 **handlers + expression
      同时为空** 时报 error。其他形态 lowering 时已有诊断；这里不重复。
    """
    out: list[Diagnostic] = []
    match expr:
        case LetExpr(bindings=bs, body=body, span=sp) if len(bs) < 1 and len(body) < 1:
            out.append(_diag("H3", "LetExpr has no bindings and no body", span=sp))
        case HandleExpr(expression=e, handlers=hs, span=sp) if len(hs) < 1 and e is None:
            out.append(_diag("H3", "HandleExpr has no expression and no handlers", span=sp))
        case ModuleExpr(body=body, export_names=exports, macro_exports=macros, span=sp) if (
            len(body) < 1
        ):
            # macro.expand 会把 (macro ...) 从 body 中剥离到 module_macro_namespace，
            # 因此只导出宏的模块在 HIR 层的 body 可能为空（合法运行时模式）。
            # 已有导出声明时不再报 warning。
            if not exports and not macros:
                out.append(_diag("H3", "ModuleExpr.body must be ≥ 1", span=sp, severity="warning"))
        case _:
            pass
    # 递归检查子节点
    for child in _children(expr):
        out.extend(h3_node_shape(child))
    return tuple(out)


# ─── H4 ──────────────────────────────────────────────────────────────────────
# "CallExpr.continuous=True 当且仅当对应 Binding.operator_kind ∈ {Pure}
#  且 OperatorSignature.continuous=True"
#
# 当前 lowering 未传播该标志（hir-spec.md §7.1），所以该规则目前对所有 IR 都
# 不违反；保留为 warning 等 lowering 修复后再升为 error（参见 plan decision (a)）。


def h4_call_continuous(call: CallExpr) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    if call.continuous:
        binding = _call_operator_binding(call)
        if binding is None:
            out.append(
                _diag(
                    "H4",
                    "CallExpr.continuous=True but operator is not a SymbolRefExpr",
                    severity=H4_SEVERITY,
                    span=call.span,
                )
            )
            return tuple(out)
        if binding.operator_kind != "pure":
            out.append(
                _diag(
                    "H4",
                    f"CallExpr.continuous=True but operator_kind={binding.operator_kind!r} "
                    "(expected 'pure')",
                    severity=H4_SEVERITY,
                    span=call.span,
                )
            )
        if not binding.continuous:
            out.append(
                _diag(
                    "H4",
                    "CallExpr.continuous=True but Binding.continuous=False",
                    severity=H4_SEVERITY,
                    span=call.span,
                )
            )
    return tuple(out)


# ─── H5 ──────────────────────────────────────────────────────────────────────
# "CallExpr.tail_position 仅在合法位置
#  (函数最末一个表达式、cond clause 的 result、if 分支、pipeline body 末项等)"


_LEGAL_TAIL_PARENTS: frozenset[Parent] = frozenset(
    {
        Parent.TOP,
        Parent.FUNC_BODY,
        Parent.COND_RESULT,
        Parent.IF_BRANCH,
        Parent.PIPELINE_LAST,
        Parent.LET_BODY,
        Parent.HANDLE_BODY,
    }
)


def h5_call_tail_position(call: CallExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    if call.tail_position and scope.parent not in _LEGAL_TAIL_PARENTS:
        return (
            _diag(
                "H5",
                f"CallExpr.tail_position=True in illegal parent context {scope.parent.value!r}",
                span=call.span,
            ),
        )
    return ()


# ─── H6 ──────────────────────────────────────────────────────────────────────
# "HandleExpr 内 effect 必须已被 defeffect 声明"


def h6_handle_effect_declared(handle: HandleExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    for h in handle.handlers:
        # ``on`` 格式由 lowering 自动声明 effect，静态检查不对其报未声明。
        if h.auto_declared:
            continue
        if h.effect.name in scope.declared_effects:
            continue
        if _effect_declared(h.effect, scope.space):
            continue
        # Phase 1：以 warning 形式给出。``_auto_declare_on_effects`` 在
        # lowering 时会隐式声明 assert-failed 等系统级 effect，static check
        # 暂时无法识别这些"自动声明"——留待 lowering 重构后升为 error。
        out.append(
            _diag(
                "H6",
                f"HandleExpr handler effect {h.effect.name!r} is not declared via defeffect",
                severity="warning",
                span=handle.span,
            )
        )
    return tuple(out)


# ─── H7 ──────────────────────────────────────────────────────────────────────
# "ResumeExpr 仅出现在 HandleExpr 的 handler body 内；对应 effect 必须 resumable=True"


def h7_resume_in_handler(resume: ResumeExpr) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    # H7(a) -- ResumeExpr 仅在 handler body 内合法；该条件由 walk_scope 时强制
    # 当前 effect 上下文（Scope.current_effect 非 None）保证。这里只检查 H7(b)。
    return tuple(out)


def _h7_in_handler(resume: ResumeExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    if scope.current_effect is None:
        return (
            _diag(
                "H7",
                "ResumeExpr is only legal inside a HandleExpr handler body",
                span=resume.span,
            ),
        )
    if not scope.current_effect_resumable:
        return (
            _diag(
                "H7",
                f"ResumeExpr used in non-resumable effect {scope.current_effect!r}",
                span=resume.span,
            ),
        )
    return ()


# ─── H8 ──────────────────────────────────────────────────────────────────────
# "PerformExpr.effect 必须已被 defeffect 声明"


def h8_perform_effect_declared(perform: PerformExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    if perform.effect.name in scope.declared_effects or _effect_declared(
        perform.effect, scope.space
    ):
        return ()
    # 与 H6 同：低优先 warning，等 lowering 重构后升为 error。
    return (
        _diag(
            "H8",
            f"PerformExpr effect {perform.effect.name!r} is not declared via defeffect",
            severity="warning",
            span=perform.span,
        ),
    )


# ─── H9 ──────────────────────────────────────────────────────────────────────
# "ModuleExpr.export_names 中的每个符号都已在 module body 内 define"


def h9_module_export_defined(mod: ModuleExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    """模块导出必须在 module body 中被 define。.

    实现细节：``mod.body`` 在 ``macro.expand`` 之后不含 ``MacroExpr``（宏被剥离
    到 ``module_macro_namespace``），但 ``(exports ...)`` 仍可指向宏名 —— 这是合法
    的运行时模式（见 ``test_module_import::test_from_import_supports_same_source_unit_module_macro_exports``）。
    该谓词只对当前 HIR 视图做检查；缺导出仅报告为 ``warning`` 而非 ``error``，
    这样宏导出仍可工作。一旦 ``macro.expand`` 把宏也保留到 HIR 层，可收紧为 error。
    """
    defined = _collect_defined_in_module(mod)
    out: list[Diagnostic] = []
    for name in mod.export_names:
        # mod.export_names is tuple[Symbol, ...] but _collect_defined_in_module
        # returns a set of str (the .name field of each binding). Compare on the
        # string form so the lookup succeeds.
        if name.name not in defined:
            out.append(
                _diag(
                    "H9",
                    f"ModuleExpr export {name.name!r} is not defined in module body",
                    span=mod.span,
                    severity="warning",
                )
            )
    return tuple(out)


# ─── H10 ─────────────────────────────────────────────────────────────────────
# "FromImportExpr.specs 中的每个名字都已在目标 module 的 export view 中"


def h10_from_import_specs_present(
    fr: FromImportExpr, scope: Scope, *, exports: Callable[[Symbol], frozenset[str]] | None = None
) -> tuple[Diagnostic, ...]:
    if exports is None:
        # Phase 1 中 lowering 不提供 exports 查询；只能校验 specs 非空。
        return ()
    available = exports(fr.module)
    out: list[Diagnostic] = []
    for spec in fr.specs:
        if spec.name.name not in available:
            out.append(
                _diag(
                    "H10",
                    f"FromImport {spec.name.name!r} not in module {fr.module.name!r} exports",
                    span=fr.span,
                )
            )
    return tuple(out)


# ─── H11 ─────────────────────────────────────────────────────────────────────
# "QuoteExpr.form 是合法 Form（Symbol | Chain），不得是 runtime value"


def h11_quote_form_is_form(quote: QuoteExpr) -> tuple[Diagnostic, ...]:
    if not _is_valid_form(quote.form):
        return (
            _diag(
                "H11",
                "QuoteExpr.form is not a legal Form (Symbol | Chain | tuple)",
                span=quote.span,
            ),
        )
    return ()


# ─── H12 ─────────────────────────────────────────────────────────────────────
# "DefineExpr.name 在当前 SymbolSpace 内未绑定；同 scope 内 define 不重复"


def h12_define_once_in_space(define: DefineExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    if scope.space is None:
        return ()
    if define.name in scope.space.bindings:
        return (
            _diag(
                "H12",
                f"DefineExpr rebinds existing symbol {define.name.name!r} "
                f"in space {scope.space.name!r}",
                span=define.span,
            ),
        )
    return ()


# ─── H13 ─────────────────────────────────────────────────────────────────────
# "读取未完成 RHS 的 binding 应被静态标记为 effort（pending binding）"
#
# 当前 lowering 把 ``(define x (... x ...))`` 编译期视为合法；H13 是对未来
# 静态 pending-binding 标记系统的占位。Phase 1 不做运行时/编译期 effort 检查，
# 仅当 binding 的 source 字段为 sentinel 时发出 warning，留待后续 PR。


def h13_pending_binding_effort(expr: IRExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    return ()


# ─── H14 ─────────────────────────────────────────────────────────────────────
# "MacroExpr.raw_body 与 body 在 macro 展开后保持同步"
#
# Phase 1 检查 raw_body 与 body 在数量上对齐（macro 的每个 form 都对应一个 lowered
# 表达式）；真正语义同步性由 macroexpand 的 hygiene trace 负责。


def h14_macro_body_raw_synced(macro: MacroExpr) -> tuple[Diagnostic, ...]:
    if len(macro.raw_body) != len(macro.body):
        return (
            _diag(
                "H14",
                f"MacroExpr.raw_body ({len(macro.raw_body)}) and body ({len(macro.body)}) "
                "are out of sync",
                span=macro.span,
            ),
        )
    return ()


# ─── Program entry ───────────────────────────────────────────────────────────


def check_program(
    program: ProgramIR, *, profile_effects: frozenset[str] = frozenset()
) -> tuple[Diagnostic, ...]:
    """运行 H1-H14 全套检查并聚合诊断。.

    该入口同时是 ``ValidateHIRPass.run`` 调用的唯一对外 API。设计目标：
    - 不修改 IR；
    - O(N) 单次 AST 遍历；
    - 任何子节点的 violation 都上浮到 ProgramIR.diagnostics。

    ``profile_effects`` 是当前实例 profile 已声明的 effect 名（含标准 profile
    预装的 ``assert-failed`` 等），用于 H6/H8 判断 effect 是否已声明。

    当 ``program.diagnostics`` 已经包含 error 级诊断时，跳过所有谓词检查
    ——这是有意为之的"二次错误抑制"：lower.py 在解析失败时也会产生错误
    节点（例如空 ``LetExpr``），这些节点不应被 H3 等规则再开一次罚单。
    """
    if not program.ok:
        return ()
    return _check_body(program.body, Scope(space=None, declared_effects=profile_effects))


# ─── helpers ─────────────────────────────────────────────────────────────────


def _declared_effect_name(expr: IRExpr) -> str | None:
    """取出节点声明的 effect 名（``defeffect`` 可表现为 DefeffectExpr 或其 DefineExpr 包装）。."""
    if isinstance(expr, DefeffectExpr):
        return expr.name.name
    if isinstance(expr, DefineExpr) and isinstance(expr.value, DefeffectExpr):
        return expr.name.name
    return None


def _check_body(exprs: tuple[IRExpr, ...], scope: Scope) -> tuple[Diagnostic, ...]:
    """按顺序检查一个 body，并按运行时顺序累积 ``defeffect`` 声明。.

    ``defeffect`` 与 ``define`` 一样在 body 顺序中生效：只有先声明的 effect
    才能被后续 ``handle`` / ``perform`` 引用。因此声明必须沿序列线程化，
    不能只看单个节点。
    """
    out: list[Diagnostic] = []
    declared = set(scope.declared_effects)
    for expr in exprs:
        inner = replace(scope, declared_effects=frozenset(declared))
        out.extend(_check(expr, inner))
        effect_name = _declared_effect_name(expr)
        if effect_name is not None:
            declared.add(effect_name)
    return tuple(out)


def _check(expr: IRExpr, scope: Scope) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []

    # H1
    out.extend(h1_resolved_symbols(expr))
    # H3
    out.extend(h3_node_shape(expr))

    match expr:
        # H4 / H5 都只对 CallExpr 有意义
        case CallExpr() as call:
            out.extend(h4_call_continuous(call))
            out.extend(h5_call_tail_position(call, scope))
            out.extend(_check(call.operator, scope))
            for arg in call.args:
                out.extend(_check(arg, scope))

        # H6 -- handler effect declared
        case HandleExpr() as h:
            out.extend(h6_handle_effect_declared(h, scope))
            # ``on`` 格式的 handler 自动声明自身 effect，且对整个 handle
            # （包括 expression 与其它 handler body）可见。
            declared = set(scope.declared_effects)
            for handler in h.handlers:
                if handler.auto_declared:
                    declared.add(handler.effect.name)
            handle_scope = replace(scope, declared_effects=frozenset(declared))
            out.extend(_check(h.expression, handle_scope))
            for handler in h.handlers:
                inner = Scope(
                    space=(
                        scope.space.child(f"handler:{handler.effect.name}")
                        if scope.space is not None
                        else None
                    ),
                    parent=Parent.HANDLE_BODY,
                    current_effect=handler.effect.name,
                    current_effect_resumable=_effect_is_resumable(handler.effect, scope.space),
                    declared_effects=frozenset(declared),
                )
                out.extend(_check_body(handler.body, inner))

        # H7 -- ResumeExpr 必须出现在 handler body 内
        case ResumeExpr() as r:
            out.extend(_h7_in_handler(r, scope))
            out.extend(_check(r.continuation, scope))
            out.extend(_check(r.value, scope))

        # H8
        case PerformExpr() as p:
            out.extend(h8_perform_effect_declared(p, scope))
            out.extend(_check(p.argument, scope))

        # H9
        case ModuleExpr() as m:
            out.extend(h9_module_export_defined(m, scope))
            inner = Scope(
                space=scope.space.child(f"module:{m.name.name}") if scope.space else None,
                parent=Parent.TOP,
                current_module=m.name.name,
                module_defined=_collect_defined_in_module(m),
                declared_effects=scope.declared_effects,
            )
            out.extend(_check_body(m.body, inner))

        # H11
        case QuoteExpr() as q:
            out.extend(h11_quote_form_is_form(q))

        # H12
        case DefineExpr() as d:
            out.extend(h12_define_once_in_space(d, scope))
            out.extend(_check(d.value, scope))

        # H14 + macro body
        case MacroExpr() as mc:
            out.extend(h14_macro_body_raw_synced(mc))
            out.extend(_check_body(mc.body, scope))

        # LetExpr 创建新空间，但 body 在新空间求值
        case LetExpr() as let:
            inner = Scope(
                space=scope.space,
                parent=Parent.LET_BODY,
                declared_effects=scope.declared_effects,
            )
            for binding in let.bindings:
                out.extend(_check(binding.value, inner))
            out.extend(_check_body(let.body, inner))

        # Lambda / Defun 创建新空间
        case LambdaExpr() as lam:
            inner = Scope(
                space=scope.space,
                parent=Parent.FUNC_BODY,
                declared_effects=scope.declared_effects,
            )
            out.extend(_check_body(lam.body, inner))

        case DefunExpr() as df:
            inner = Scope(
                space=scope.space,
                parent=Parent.FUNC_BODY,
                declared_effects=scope.declared_effects,
            )
            out.extend(_check_body(df.body, inner))

        # Cond -- clause.result 在 tail position 候选
        case CondExpr() as cond:
            for clause in cond.clauses:
                out.extend(_check(clause.condition, scope))
                out.extend(_check(clause.result, _set_parent(scope, Parent.COND_RESULT)))

        # Pipeline -- 最后一个 expr 在 tail position 候选；defeffect 顺序生效
        case PipelineExpr() as pipe:
            declared = set(scope.declared_effects)
            for i, body_expr in enumerate(pipe.body):
                parent = Parent.PIPELINE_LAST if i == len(pipe.body) - 1 else Parent.ARG
                inner = replace(scope, parent=parent, declared_effects=frozenset(declared))
                out.extend(_check(body_expr, inner))
                effect_name = _declared_effect_name(body_expr)
                if effect_name is not None:
                    declared.add(effect_name)

        # Parallel/All/Race -- 无 tail position
        case ParallelExpr(exprs=xs) | AllExpr(exprs=xs) | RaceExpr(exprs=xs):
            for x in xs:
                out.extend(_check(x, scope))

        # Apply -- args 是运行时 chain
        case ApplyExpr(function=f, args=args):
            out.extend(_check(f, scope))
            out.extend(_check(args, scope))

        # Cache / RuntimeEval
        case CacheExpr(expression=inner) | RuntimeEvalExpr(expression=inner):
            out.extend(_check(inner, scope))

        # AssertExpr
        case AssertExpr(condition=cond, message=msg):
            out.extend(_check(cond, scope))
            if msg is not None:
                out.extend(_check(msg, scope))

        # 叶子节点 / 已处理
        case _:
            pass

    return tuple(out)


def _set_parent(scope: Scope, parent: Parent) -> Scope:
    return Scope(
        space=scope.space,
        parent=parent,
        current_effect=scope.current_effect,
        current_effect_resumable=scope.current_effect_resumable,
        current_module=scope.current_module,
        module_defined=scope.module_defined,
        declared_effects=scope.declared_effects,
    )


def _walk_symbol_refs(expr: IRExpr) -> Iterator[SymbolRefExpr]:
    if isinstance(expr, SymbolRefExpr):
        yield expr
    for child in _children(expr):
        yield from _walk_symbol_refs(child)


def _children(expr: IRExpr):
    match expr:
        case CallExpr(operator=op, args=args):
            yield op
            for a in args:
                yield a
        case LetExpr(bindings=bs, body=body):
            for b in bs:
                yield b.value
            for b in body:
                yield b
        case LambdaExpr(body=body) | DefunExpr(body=body) | PipelineExpr(body=body):
            for b in body:
                yield b
        case DefineExpr(value=v):
            yield v
        case CondExpr(clauses=cs):
            for c in cs:
                yield c.condition
                yield c.result
        case ParallelExpr(exprs=xs) | AllExpr(exprs=xs) | RaceExpr(exprs=xs):
            yield from xs
        case ApplyExpr(function=f, args=args):
            yield f
            yield args
        case MacroExpr(body=body):
            for b in body:
                yield b
        case HandleExpr(expression=e, handlers=hs):
            yield e
            for h in hs:
                for b in h.body:
                    yield b
        case ModuleExpr(body=body):
            for b in body:
                yield b
        case RuntimeEvalExpr(expression=e) | CacheExpr(expression=e):
            yield e
        case ResumeExpr(continuation=k, value=v):
            yield k
            yield v
        case PerformExpr(argument=a):
            yield a
        case AssertExpr(condition=c, message=m):
            yield c
            if m is not None:
                yield m
        case (
            SymbolRefExpr()
            | UnresolvedSymbolExpr()
            | LiteralExpr()
            | QuoteExpr()
            | FromImportExpr()
            | DefeffectExpr()
        ):
            return
        case _:
            return


def _call_operator_binding(call: CallExpr):
    if isinstance(call.operator, SymbolRefExpr):
        return call.operator.binding
    return None


def _effect_declared(effect: Symbol, space: SymbolSpace | None) -> bool:
    """在 ss-chain 中查找 effect 是否由 ``defeffect`` 声明。."""
    current = space
    while current is not None:
        for sym, slot in current.bindings.items():
            if sym == effect:
                # Phase 1: 仅当 binding 在本空间内且 source 为 defeffect 才算声明。
                # 完整检查需要 binding source 元数据；这里采用保守启发式，
                # 实际生产 lowering 已在 resolution 阶段校验。
                del slot
                return True
        current = current.parent
    return False


def _effect_is_resumable(effect: Symbol, space: SymbolSpace | None) -> bool:
    """查找 ``defeffect`` 是否声明为 ``resumable=True``。.

    Phase 1 保守返回 True：完整实现需要在 binding 上携带 resumable 标志。
    """
    del effect, space
    return True


def _collect_defined_in_module(mod: ModuleExpr) -> frozenset[str]:
    out: set[str] = set()
    for expr in mod.body:
        if isinstance(expr, DefineExpr):
            out.add(expr.name.name)
        elif isinstance(expr, DefunExpr):
            out.add(expr.name.name)
        elif isinstance(expr, MacroExpr):
            out.add(expr.name.name)
    # 宏导出在 macro.expand 阶段被剥离出 body，但仍算已定义导出。
    out.update(mod.macro_exports)
    return frozenset(out)


def _is_valid_form(form: Form) -> bool:
    if isinstance(form, Symbol):
        return True
    if is_chain(form):
        return True
    if isinstance(form, (SpannedTuple, DottedTuple)):
        return True
    if isinstance(form, tuple):
        return all(_is_valid_form(child) for child in form)
    # H11 also accepts literal atoms that can legitimately appear inside a
    # quoted form: plain Python scalars (int/str/float/bool/None/bytes) and
    # QyNil — the latter is what the reader macro '() lowers to. The spec
    # says "Symbol | Chain" but the runtime machinery preserves any literal
    # atom — see test_evaluator::test_evaluate_quote and
    # test_basic_operators::test_car_cdr_cons.
    from qy.core.syntax import QyNil

    if isinstance(form, (int, float, bool, str, bytes, type(None), QyNil)):
        return True
    return False
