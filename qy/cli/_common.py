# -*- coding: utf-8 -*-

"""CLI 共享工具与常量."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from qy.analysis import Diagnostic
from qy.async_utils import run_coro
from qy.passes.build import compile_source_to_kind_async
from qy.passes.pass_base import PipelineSession
from qy.runtime import Qy

CLI_COMMANDS = (
    "run",
    "repl",
    "expand",
    "hir",
    "mir",
    "lir",
    "bytecode",
    "export",
    "llvm",
    "fmt",
    "ast",
    "check",
    "typecheck",
    "operators",
    "lsp",
    "completion",
)
REPL_COMMANDS = (".help", ".env", ".ast", ".fmt", ".check", ".exit", ".quit")


def _is_definition_artifact(value: object) -> bool:
    """Skip top-level results coming from binding-form evaluation.

    ``defun`` / ``define`` / ``from`` / ``module`` and the like emit a
    BytecodeFunctionValue / StandardModule / EffectDefinition / MacroDefinition
    as a side product of their lowering. They are not user-visible expression
    values and the CLI ``run`` command should not print them.
    """
    from qy.import_.module import StandardModule
    from qy.macro import MacroDefinition
    from qy.sem.runtime import EffectDefinition
    from qy.vm.bytecode import BytecodeFunctionValue

    return (
        isinstance(
            value,
            BytecodeFunctionValue | StandardModule | EffectDefinition | MacroDefinition,
        )
        or value is None
    )


def read_debug_source(target: str) -> tuple[str, str]:
    import typer

    try:
        if target == "-":
            return sys.stdin.read(), "<stdin>"
        path = Path(target)
        return path.read_text(encoding="utf-8"), str(path)
    except OSError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e


def compile_source_to(qy: Qy, source: str, *, kind: str, source_name: str) -> Any:
    """Run the standard pipeline against ``source`` until ``kind`` is produced.

    Returns the raw ``PassResult`` so callers can inspect ``diagnostics`` together
    with the typed artifact extractor.
    """
    session = PipelineSession(env=qy.env, source_name=source_name)
    return run_coro(compile_source_to_kind_async(source, session, kind=kind))


def print_debug_diagnostics(source_name: str, diagnostics: tuple[Diagnostic, ...]) -> bool:
    import typer

    has_errors = False
    for diagnostic in diagnostics:
        typer.secho(
            format_diagnostic(source_name, diagnostic),
            fg=diagnostic_color(diagnostic),
            err=True,
        )
        has_errors = has_errors or diagnostic.severity == "error"
    return has_errors


def format_diagnostic(path: str | Path, diagnostic: Diagnostic) -> str:
    location = str(path)
    if diagnostic.line is not None and diagnostic.column is not None:
        location = f"{location}:{diagnostic.line}:{diagnostic.column}"
    return f"{location}: {diagnostic.severity}: {diagnostic.message}"


def diagnostic_color(diagnostic: Diagnostic) -> str:
    import typer

    if diagnostic.severity == "warning":
        return typer.colors.YELLOW
    if diagnostic.severity == "hint":
        return typer.colors.BLUE
    return typer.colors.RED
