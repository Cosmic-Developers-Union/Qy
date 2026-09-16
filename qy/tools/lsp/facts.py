# coding: utf-8
"""LSP 的 canonical document facts。.

LSP 的 completion / hover / document symbol 必须与 `qy check`、analyzer、CLI
读取同一份事实：canonical frontend（CST → surface dialect → macro expand）+ HIR。
本模块把这份事实抽出来，避免各 feature 各自用裸 reader 重新解释源码。

当前提供：

- ``document_locals``：文档内所有 lexical binding（`define` / `let` / 参数 /
  handler 参数 / `defeffect` / `defun`），带定义点 span 与来源标签；
- ``macro_expanded_forms``：macro expand 之后的 core forms（供需要"宏展开后视图"
  的 feature 使用）。

禁止：
- 不得在这里定义语言语义（解析、作用域规则都属于 canonical frontend / HIR）。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields
from dataclasses import is_dataclass

from qy.async_utils import run_coro
from qy.build.pipeline import compile_source_to_kind_async
from qy.build.pipeline import core_ast_artifact
from qy.build.pipeline import hir_artifact
from qy.core.syntax import Symbol
from qy.errors import SourceSpan
from qy.ir.hir import DefeffectExpr
from qy.ir.hir import DefineExpr
from qy.ir.hir import DefunExpr
from qy.ir.hir import EffectHandler
from qy.ir.hir import LambdaExpr
from qy.ir.hir import LetBinding
from qy.passes.pass_base import PipelineSession
from qy.runtime import Qy
from qy.tools.lsp.utils import shared_instance

__all__ = ["LocalBinding", "document_locals", "macro_expanded_forms"]


@dataclass(frozen=True, slots=True)
class LocalBinding:
    """文档内一个 lexical binding 的定义点。."""

    name: str
    source: str
    span: SourceSpan | None

    @property
    def line(self) -> int | None:
        return None if self.span is None else self.span.start_line


def _session(qy: Qy | None) -> PipelineSession:
    runtime = qy or shared_instance()
    return PipelineSession(env=runtime.env)


def _add(bindings: list[LocalBinding], symbol: object, kind: str) -> None:
    if isinstance(symbol, Symbol):
        bindings.append(LocalBinding(symbol.name, kind, symbol.span))


def _collect(node: object, bindings: list[LocalBinding]) -> None:
    """Walk HIR nodes and record every lexical binding definition site."""
    if isinstance(node, DefineExpr):
        _add(bindings, node.name, "define")
    elif isinstance(node, DefunExpr):
        _add(bindings, node.name, "defun")
    elif isinstance(node, LetBinding):
        _add(bindings, node.symbol, "let-binding")
    elif isinstance(node, LambdaExpr):
        for param in node.params:
            _add(bindings, param, "lambda-param")
    elif isinstance(node, DefeffectExpr):
        _add(bindings, node.name, "defeffect")
    elif isinstance(node, EffectHandler):
        _add(bindings, node.arg_name, "handler-arg")
        _add(bindings, node.continuation_name, "handler-continuation")

    if is_dataclass(node) and not isinstance(node, type):
        for field_info in fields(node):
            _collect(getattr(node, field_info.name), bindings)
    elif isinstance(node, tuple | list):
        for item in node:
            _collect(item, bindings)


def document_locals(source: str, *, qy: Qy | None = None) -> tuple[LocalBinding, ...]:
    """Return every lexical binding defined in *source* (canonical pipeline)."""
    result = run_coro(compile_source_to_kind_async(source, _session(qy), kind="hir"))
    if any(diagnostic.severity == "error" for diagnostic in result.diagnostics):
        return ()
    program = hir_artifact(result)

    bindings: list[LocalBinding] = []
    for item in program.body:
        _collect(item, bindings)

    # 同一个定义点可能既被外层 DefineExpr 又被内层专门节点记录（例如
    # ``defeffect``）；按 (name, span) 去重并保留更专门的后一次记录。
    deduped: dict[tuple[str, int | None, int | None], LocalBinding] = {}
    for binding in bindings:
        span = binding.span
        key = (
            binding.name,
            None if span is None else span.start_line,
            None if span is None else span.start_column,
        )
        deduped[key] = binding
    return tuple(deduped.values())


def macro_expanded_forms(source: str, *, qy: Qy | None = None) -> tuple[object, ...]:
    """Return macro-expanded core forms; empty when expansion fails."""
    result = run_coro(compile_source_to_kind_async(source, _session(qy), kind="core-ast"))
    if any(diagnostic.severity == "error" for diagnostic in result.diagnostics):
        return ()
    return tuple(core_ast_artifact(result).forms)
