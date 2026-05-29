# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from qy.async_utils import run_coro
from qy.backend.vm.bytecode import BytecodeProgram
from qy.core.operator_signature import OperatorSignature
from qy.core.operators import ArgumentEvaluator
from qy.core.symbol_space import ChainFrame
from qy.errors import QyResolveError
from qy.errors import QyRuntimeError
from qy.errors import SourceSpan
from qy.errors import TraceFrame
from qy.frontend.reader import Form
from qy.frontend.reader import read
from qy.frontend.reader import read_one
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.session.runtime_space import create_standard_runtime_space as standard_environment
from qy.vm.instance.machine import RegisterVirtualMachine
from qy.vm.instance.machine import evaluate_bytecode_async

__all__ = [
    "AsyncQy",
    "Qy",
    "evaluate",
    "evaluate_async",
    "evaluate_body",
    "evaluate_body_async",
    "evaluate_file",
    "evaluate_file_async",
    "evaluate_program",
    "evaluate_program_async",
    "evaluate_source",
    "evaluate_source_async",
]


class _QyBase:
    def __init__(self, env: Environment | None = None) -> None:
        self.env = env or standard_environment()

    @property
    def pre_symbol_space_chain(self) -> tuple[ChainFrame, ...]:
        return self.env.pre_symbol_space_chain()

    def read(self, source: str) -> list[Form]:
        return read(source)

    def read_one(self, source: str) -> Form:
        return read_one(source)

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
        argument_evaluator: ArgumentEvaluator | None = None,
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_pure(
            name,
            func,
            doc=doc,
            argument_evaluator=argument_evaluator,
            signature=signature,
        )
        if func is None:
            return registered
        return func

    def register_scope(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_scope(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_control(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_control(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_effect(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_effect(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_meta(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_meta(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_evaluation(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        return self.register_control(name, func, doc=doc, signature=signature)

    def register_syntax(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        return self.register_meta(name, func, doc=doc, signature=signature)


class Qy(_QyBase):
    def evaluate(self, expression: object) -> object:
        return run_coro(_evaluate_form_via_pipeline(expression, self.env))

    def evaluate_source(self, source: str, *, source_name: str | None = None) -> object:
        return run_coro(evaluate_source_async(source, self.env, source_name=source_name))

    async def evaluate_source_async(self, source: str, *, source_name: str | None = None) -> object:
        return await evaluate_source_async(source, self.env, source_name=source_name)

    def evaluate_program(self, source: str, *, source_name: str | None = None) -> list[object]:
        return cast(
            list[object],
            run_coro(_evaluate_program_via_pipeline(source, self.env, source_name=source_name)),
        )

    def evaluate_file(self, path: str | Path) -> object:
        path = Path(path)
        results = self.evaluate_program(
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        if not results:
            return None
        return results[-1]

    def fmt(self, source: str) -> str:
        from qy.tools.fmt import format_source

        return format_source(source)


class AsyncQy(_QyBase):
    async def evaluate(self, expression: object) -> object:
        return await _evaluate_form_via_pipeline(expression, self.env)

    async def evaluate_source(self, source: str, *, source_name: str | None = None) -> object:
        return await evaluate_source_async(source, self.env, source_name=source_name)

    evaluate_source_async = evaluate_source

    async def evaluate_program(
        self, source: str, *, source_name: str | None = None
    ) -> list[object]:
        return await _evaluate_program_via_pipeline(source, self.env, source_name=source_name)

    async def evaluate_file(self, path: str | Path) -> object:
        path = Path(path)
        results = await self.evaluate_program(
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        return None if not results else results[-1]

    def fmt(self, source: str) -> str:
        from qy.tools.fmt import format_source

        return format_source(source)


# -- Standalone evaluation API ------------------------------------------------


def _raise_on_diagnostics(diagnostics: tuple[object, ...]) -> None:
    from qy.analysis import Diagnostic

    errors = tuple(
        item for item in diagnostics if isinstance(item, Diagnostic) and item.severity == "error"
    )
    if not errors:
        return
    if len(errors) == 1 and errors[0].message.startswith("unresolved symbol "):
        symbol = errors[0].message.removeprefix("unresolved symbol ").strip("'")
        span = SourceSpan(start_line=errors[0].line, start_column=errors[0].column)
        raise QyResolveError(
            errors[0].message,
            span=span,
            frames=(TraceFrame("call", None, span),),
            metadata={"symbol": symbol},
        )
    messages = "; ".join(item.message for item in errors)
    first = errors[0]
    raise QyRuntimeError(
        f"cannot evaluate program with diagnostics: {messages}",
        span=SourceSpan(start_line=first.line, start_column=first.column),
    )


def evaluate(expression: object, env: Environment | None = None) -> object:
    return run_coro(evaluate_async(expression, env))


async def evaluate_async(expression: object, env: Environment | None = None) -> object:
    runtime_env = env or standard_environment()
    return await _evaluate_form_via_pipeline(expression, runtime_env)


def evaluate_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    return run_coro(evaluate_source_async(source, env, source_name=source_name))


async def evaluate_source_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> object:
    runtime_env = env or standard_environment()
    bytecode, pipeline_diagnostics = await _compile_source_via_pipeline(
        source, runtime_env, source_name=source_name
    )
    _raise_on_diagnostics(pipeline_diagnostics)
    if bytecode is None:
        return None
    _raise_on_diagnostics(bytecode.diagnostics)
    return await evaluate_bytecode_async(bytecode, runtime_env)


def evaluate_program(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    return cast(
        list[object],
        run_coro(evaluate_program_async(source, env, source_name=source_name)),
    )


async def evaluate_program_async(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> list[object]:
    runtime_env = env or standard_environment()
    bytecode, pipeline_diagnostics = await _compile_source_via_pipeline(
        source, runtime_env, source_name=source_name
    )
    _raise_on_diagnostics(pipeline_diagnostics)
    if bytecode is None:
        return []
    _raise_on_diagnostics(bytecode.diagnostics)
    return await RegisterVirtualMachine(bytecode, runtime_env).evaluate_program()


# -- Pipeline-backed evaluation helpers -------------------------------------


async def _compile_source_via_pipeline(
    source: str,
    env: Environment,
    *,
    source_name: str | None = None,
) -> tuple[BytecodeProgram | None, tuple]:
    """Run the source-to-bytecode pipeline.

    返回 ``(bytecode_or_none, pipeline_diagnostics)``。当 pipeline 在到达
    ``emit.bytecode`` 之前因 error 阈值短路时，``bytecode`` 为 ``None``，
    全部诊断仍包含在 ``pipeline_diagnostics`` 中。
    """
    from qy.build.pipeline import compile_source_to_bytecode_async
    from qy.passes.pass_base import PipelineSession

    session = PipelineSession(env=env, source_name=source_name)
    result = await compile_source_to_bytecode_async(source, session)
    if isinstance(result.artifact, BytecodeProgram):
        return result.artifact, tuple(result.diagnostics)
    return None, tuple(result.diagnostics)


async def _evaluate_program_via_pipeline(
    source: str,
    env: Environment,
    *,
    source_name: str | None = None,
) -> list[object]:
    """``Qy.evaluate_program`` 走的宽松路径：pipeline 诊断不抛错（保持旧行为）。."""
    bytecode, _ = await _compile_source_via_pipeline(source, env, source_name=source_name)
    if bytecode is None:
        return []
    return await RegisterVirtualMachine(bytecode, env).evaluate_program()


async def _evaluate_form_via_pipeline(expression: object, env: Environment) -> object:
    from qy.vm.instance.machine import evaluate_form_async

    return await evaluate_form_async(expression, env)


def evaluate_file(path: str | Path, env: Environment | None = None) -> object:
    return run_coro(evaluate_file_async(path, env))


async def evaluate_file_async(path: str | Path, env: Environment | None = None) -> object:
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    results = await evaluate_program_async(source, env, source_name=str(path))
    if not results:
        return None
    return results[-1]


def evaluate_body(body: tuple[object, ...], env: Environment) -> object:
    from qy.vm.instance.machine import evaluate_form_body_async

    return run_coro(evaluate_form_body_async(body, env))


async def evaluate_body_async(body: tuple[object, ...], env: Environment) -> object:
    from qy.vm.instance.machine import evaluate_form_body_async

    return await evaluate_form_body_async(body, env)
