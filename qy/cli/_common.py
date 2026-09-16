# -*- coding: utf-8 -*-

"""CLI 共享工具与常量."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any
from typing import TextIO

import click

from qy.analysis import Diagnostic
from qy.async_utils import run_coro
from qy.build.pipeline import compile_source_to_kind_async
from qy.passes.pass_base import PipelineSession
from qy.runtime import Qy

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


def use_color(stream: TextIO | None = None) -> bool:
    """Return ``True`` if ANSI color should be emitted on ``stream``.

    Honors the standard ``NO_COLOR`` convention (``https://no-color.org/``),
    ``TERM=dumb``, and the ``--no-color`` flag exposed by the top-level CLI
    group. Falls back to ``False`` when ``stream`` is not a TTY. When in
    doubt, prefer plain text — debugging by piping through ``cat`` or
    ``less`` should never produce ANSI escapes.
    """
    target = stream if stream is not None else sys.stdout
    if not hasattr(target, "isatty") or not target.isatty():
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return True


def style(text: str, *, fg: str | None = None, bold: bool = False) -> str:
    """Wrap ``text`` in ANSI escapes when colors are enabled; return as-is otherwise.

    ``fg`` accepts the common color names used by click — ``"red"``,
    ``"green"``, ``"yellow"``, ``"blue"``, ``"cyan"``, ``"magenta"``,
    ``"white"``, ``"black"``, ``"bright_*"`` variants. Unknown values fall
    back to no styling rather than emitting broken escapes.
    """
    if not use_color():
        return text
    codes: list[str] = []
    if bold:
        codes.append("1")
    palette = {
        "black": "30",
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "magenta": "35",
        "cyan": "36",
        "white": "37",
        "bright_black": "90",
        "bright_red": "91",
        "bright_green": "92",
        "bright_yellow": "93",
        "bright_blue": "94",
        "bright_magenta": "95",
        "bright_cyan": "96",
        "bright_white": "97",
    }
    if fg in palette:
        codes.append(palette[fg])
    if not codes:
        return text
    prefix = "\x1b[" + ";".join(codes) + "m"
    suffix = "\x1b[0m"
    return f"{prefix}{text}{suffix}"


def secho(
    message: str | Any,
    *,
    fg: str | None = None,
    bold: bool = False,
    err: bool = False,
) -> None:
    """Emit ``message`` to stdout (default) or stderr.

    Falls back to ``click.echo`` when no color is requested; otherwise
    applies ``style`` first. Color decisions are TTY-aware so piped output
    never carries ANSI escapes.
    """
    text = message if isinstance(message, str) else str(message)
    if fg or bold:
        text = style(text, fg=fg, bold=bold)
    click.echo(text, err=err)


def read_debug_source(target: str) -> tuple[str, str]:
    try:
        if target == "-":
            return sys.stdin.read(), "<stdin>"
        path = Path(target)
        return path.read_text(encoding="utf-8"), str(path)
    except OSError as e:
        secho(str(e), fg="red", err=True)
        raise click.exceptions.Exit(1) from e


def compile_source_to(qy: Qy, source: str, *, kind: str, source_name: str) -> Any:
    """Run the standard pipeline against ``source`` until ``kind`` is produced.

    Returns the raw ``PassResult`` so callers can inspect ``diagnostics`` together
    with the typed artifact extractor.
    """
    session = PipelineSession(env=qy.env, source_name=source_name)
    return run_coro(compile_source_to_kind_async(source, session, kind=kind))


def print_debug_diagnostics(source_name: str, diagnostics: tuple[Diagnostic, ...]) -> bool:
    has_errors = False
    for diagnostic in diagnostics:
        secho(
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
    if diagnostic.severity == "warning":
        return "yellow"
    if diagnostic.severity == "hint":
        return "blue"
    return "red"


def terminal_width(fallback: int = 100) -> int:
    """Return the current terminal width, capped to a sensible upper bound."""
    try:
        return max(40, min(shutil.get_terminal_size((fallback, 20)).columns, 200))
    except (OSError, ValueError):
        return fallback
