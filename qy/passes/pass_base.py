# coding: utf-8
"""Pass 基础接口。.

定义统一的 pass 契约：
- ``Pass``：每个 pass 声明 name 与 input_kind/output_kind，作为静态契约。
- ``PassContext``：单个 pass 的输入上下文，承载 artifact、artifact_kind、累计 diagnostics、session、options。
- ``PassResult``：pass 输出，承载 success、artifact、artifact_kind、本次 pass 产生的 diagnostics。
- ``PipelineSession``：跨 pass 共享的可变环境（env、source_map、reader_macro_registry、macro_options）。
- ``PipelineOptions``：调度器选项（after / target / dump_sink / error_threshold）。

设计约束：
- diagnostics 使用 ``tuple[Diagnostic, ...]``，防止 pass 之间互相污染。
- ``Pipeline.run`` 只返回 ``PassResult``，**不抛异常**。诊断转异常由 ``qy.diag.raise`` 统一负责。
- ``input_kind`` / ``output_kind`` 是字符串契约，由 ``Pipeline`` 在相邻 pass 之间断言匹配。
"""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import ClassVar

from qy.diag import Diagnostic

__all__ = [
    "Pass",
    "PassContext",
    "PassResult",
    "PipelineOptions",
    "PipelineSession",
]


@dataclass(slots=True)
class PipelineSession:
    """跨 pass 共享的可变会话状态。.

    - ``env``：运行时符号空间（``qy.session.runtime_space.RuntimeSpace``），
      ``macro.expand`` / ``hir.lower`` 等 pass 通过它访问 macro 命名空间、模块等。
    - ``source_name``：当前编译单元的源文件名（用于诊断 / source span）。
    - ``source_map``：源码映射，供诊断回溯 SourceSpan / TraceFrame。
    - ``reader_macro_registry``：``frontend.reader_macro`` pass 使用的 tag 注册表。
    - ``macro_options``：``macro.expand`` 所需的展开选项（深度、effect policy 等）。

    为 Batch 1 仅作占位字段，后续 Batch 接通后由各 pass 直接读取。
    """

    env: Any = None
    source_name: str | None = None
    source_map: Any = None
    reader_macro_registry: Any = None
    macro_options: Any = None

    @classmethod
    def minimal(cls) -> PipelineSession:
        """返回不绑定任何运行时资源的最小 session，供测试使用。."""
        return cls()


@dataclass(frozen=True, slots=True)
class PipelineOptions:
    """``Pipeline.run`` 的调度选项。."""

    after: str | None = None
    target: str | None = None
    dump_sink: Callable[[str, object], None] | None = None
    error_threshold: int = 1


@dataclass(slots=True)
class PassContext:
    """单个 Pass 的输入上下文。."""

    input_artifact: object = None
    artifact_kind: str = ""
    session: PipelineSession = field(default_factory=PipelineSession.minimal)
    diagnostics: tuple[Diagnostic, ...] = ()
    options: PipelineOptions = field(default_factory=PipelineOptions)


@dataclass(slots=True)
class PassResult:
    """Pass 执行结果。.

    - ``success``：本次 pass 是否产生 fatal failure（与 diagnostics 中的 error 不冲突；
      pass 可以返回 success=True 但携带 error 级 diagnostics，由 Pipeline 的
      ``error_threshold`` 决定是否短路）。
    - ``artifact``：本次 pass 输出的 artifact。
    - ``artifact_kind``：输出 artifact 的种类标签，必须与下一个 pass 的 ``input_kind`` 一致。
    - ``diagnostics``：**本次 pass 新产生**的 diagnostics（不含上游累积）。
    """

    success: bool
    artifact: object = None
    artifact_kind: str = ""
    diagnostics: tuple[Diagnostic, ...] = ()


class Pass:
    """Pass 基类。.

    每个 pass 子类必须：
    - 在类层声明 ``input_kind`` / ``output_kind`` 字符串契约。
    - 重写 ``run(context) -> PassResult``。
    - 通过构造函数显式传入 ``name`` 或在子类中固定。

    ``name`` 用于 ``--after=<name>`` / ``--target=<name>`` 匹配，应使用
    ``namespace.action`` 形式，例如 ``hir.lower``、``effect.flatten``。
    """

    input_kind: ClassVar[str] = ""
    output_kind: ClassVar[str] = ""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, context: PassContext) -> PassResult | Awaitable[PassResult]:
        raise NotImplementedError(f"Pass {self.name!r} 未实现 run 方法")
