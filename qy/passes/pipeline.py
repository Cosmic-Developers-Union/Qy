# coding: utf-8
"""Pass pipeline 调度器。.

实现：
- 按顺序执行 pass，并在相邻 pass 之间断言 ``output_kind == input_kind``。
- ``after``：跑完命名 pass 后调用 ``options.dump_sink(name, artifact)``。
- ``target``：跑完命名 pass 后立即返回，不再继续。
- ``error_threshold``：累计 error 级 diagnostics 超过阈值时短路返回。
- ``Pipeline.subset(start, end)``：返回子 pipeline，用于 form→bytecode 等场景复用。

约束：
- ``Pipeline.run`` **不抛异常**。诊断转异常由 ``qy.diag.raise`` 统一处理。
- Pipeline 自身无副作用：所有可变状态都从 ``PassContext.session`` 读写。
- 调度器不实现具体 pass 语义。
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import cast

from qy.diag import Diagnostic
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.passes.pass_base import PipelineOptions

__all__ = ["Pipeline"]


class Pipeline:
    """Pass 调度器。."""

    def __init__(self) -> None:
        self.passes: list[Pass] = []

    def add_pass(self, pass_: Pass) -> Pipeline:
        self.passes.append(pass_)
        return self

    def subset(self, start: str | None = None, end: str | None = None) -> Pipeline:
        """返回切片子 pipeline。.

        - ``start``：第一个被纳入的 pass 名（包含）。``None`` 表示从头。
        - ``end``：最后一个被纳入的 pass 名（包含）。``None`` 表示到尾。
        - 不修改原 pipeline；新 pipeline 共享同一组 pass 实例。
        """
        if not self.passes:
            return Pipeline()

        names = [p.name for p in self.passes]
        start_idx = 0 if start is None else _index_of(names, start, "start")
        end_idx = len(self.passes) - 1 if end is None else _index_of(names, end, "end")
        if start_idx > end_idx:
            raise ValueError(f"subset start {start!r} comes after end {end!r} in pipeline")

        result = Pipeline()
        for pass_ in self.passes[start_idx : end_idx + 1]:
            result.add_pass(pass_)
        return result

    def run(self, context: PassContext) -> PassResult:
        """同步执行 pipeline。.

        若任一 pass 的 ``run`` 返回 awaitable，则抛 ``TypeError``：
        async pass 必须通过 ``run_async`` 调度。
        """
        return _run_sync(self.passes, context)

    async def run_async(self, context: PassContext) -> PassResult:
        """异步执行 pipeline。同步 pass 直接调用，async pass 自动 await。."""
        return await _run_async(self.passes, context)


def _index_of(names: list[str], target: str, kind: str) -> int:
    try:
        return names.index(target)
    except ValueError as e:
        raise ValueError(f"unknown pass {target!r} for {kind} (have {names!r})") from e


def _run_sync(passes: list[Pass], context: PassContext) -> PassResult:
    state = _PipelineState(context)
    for pass_ in passes:
        sub_context = state.sub_context_for(pass_)
        if state.kind_mismatch(pass_):
            return state.fail_with_kind_mismatch(pass_)
        result = pass_.run(sub_context)
        if isinstance(result, Awaitable):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise TypeError(f"pass {pass_.name!r} returned an awaitable; use Pipeline.run_async")
        state.absorb(pass_, result)
        if state.should_stop_after(pass_):
            return state.finalize()
    return state.finalize()


async def _run_async(passes: list[Pass], context: PassContext) -> PassResult:
    state = _PipelineState(context)
    for pass_ in passes:
        sub_context = state.sub_context_for(pass_)
        if state.kind_mismatch(pass_):
            return state.fail_with_kind_mismatch(pass_)
        outcome = pass_.run(sub_context)
        if isinstance(outcome, Awaitable):
            result = await cast(Awaitable[PassResult], outcome)
        else:
            result = outcome
        state.absorb(pass_, result)
        if state.should_stop_after(pass_):
            return state.finalize()
    return state.finalize()


class _PipelineState:
    """Pipeline 的局部可变状态。."""

    __slots__ = (
        "current_artifact",
        "current_kind",
        "diagnostics",
        "options",
        "session",
        "stopped_for_target",
        "success",
    )

    def __init__(self, context: PassContext) -> None:
        self.options: PipelineOptions = context.options
        self.session = context.session
        self.current_artifact: object = context.input_artifact
        self.current_kind: str = context.artifact_kind
        self.diagnostics: list[Diagnostic] = list(context.diagnostics)
        self.success: bool = True
        self.stopped_for_target: bool = False

    def sub_context_for(self, pass_: Pass) -> PassContext:
        return PassContext(
            input_artifact=self.current_artifact,
            artifact_kind=self.current_kind,
            session=self.session,
            diagnostics=tuple(self.diagnostics),
            options=self.options,
        )

    def kind_mismatch(self, pass_: Pass) -> bool:
        if not pass_.input_kind:
            return False
        if not self.current_kind:
            # First pass; accept whatever arrives. The pass itself may still
            # validate by inspecting context.input_artifact.
            return False
        return pass_.input_kind != self.current_kind

    def fail_with_kind_mismatch(self, pass_: Pass) -> PassResult:
        message = (
            f"pass {pass_.name!r} expects artifact kind {pass_.input_kind!r}, "
            f"got {self.current_kind!r}"
        )
        self.diagnostics.append(Diagnostic(message, "error"))
        self.success = False
        return self.finalize()

    def absorb(self, pass_: Pass, result: PassResult) -> None:
        self.diagnostics.extend(result.diagnostics)
        self.current_artifact = result.artifact
        if result.artifact_kind:
            self.current_kind = result.artifact_kind
        elif pass_.output_kind:
            self.current_kind = pass_.output_kind
        if not result.success:
            self.success = False
        if self.options.after == pass_.name and self.options.dump_sink is not None:
            self.options.dump_sink(pass_.name, self.current_artifact)
        if self._error_count() >= self.options.error_threshold:
            self.success = False

    def should_stop_after(self, pass_: Pass) -> bool:
        if self.options.target == pass_.name:
            self.stopped_for_target = True
            return True
        if not self.success:
            return True
        return False

    def finalize(self) -> PassResult:
        return PassResult(
            success=self.success,
            artifact=self.current_artifact,
            artifact_kind=self.current_kind,
            diagnostics=tuple(self.diagnostics),
        )

    def _error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "error")
