# -*- coding: utf-8 -*-

"""`qy repl` 命令入口。."""

from __future__ import annotations

import atexit
import sys
from pathlib import Path
from typing import Any

import click

from qy.analysis import analyze_source
from qy.cli._common import REPL_COMMANDS
from qy.cli._common import diagnostic_color
from qy.cli._common import secho
from qy.cli._common import style
from qy.display import format_value
from qy.errors import QyError
from qy.errors import format_qy_error
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import read
from qy.frontend.reader import read_raw
from qy.runtime import Qy
from qy.tools.fmt import dump_program
from qy.tools.fmt import format_source


def repl(qy: Qy) -> int:
    _install_repl_readline(qy)
    secho("Qy interactive interpreter", bold=True)
    secho("Commands: .help .env .ast <expr> .fmt <expr> .check <expr> .exit")
    while True:
        try:
            source = _read_repl_source()
        except (EOFError, KeyboardInterrupt):
            click.echo()
            return 0

        source = source.strip()
        if not source:
            continue
        if source in {".exit", ".quit"}:
            return 0
        if source == ".help":
            _print_repl_help()
            continue
        if source == ".env":
            _print_environment(qy)
            continue
        if source.startswith(".ast "):
            _print_repl_ast(source[5:])
            continue
        if source.startswith(".fmt "):
            _print_repl_format(source[5:])
            continue
        if source.startswith(".check "):
            _print_repl_check(source[7:])
            continue

        try:
            for form in read(source):
                click.echo(format_value(qy.evaluate(form)))
        except QyError as e:
            secho(format_qy_error(e), fg="red", err=True)


def _read_repl_source() -> str:
    return input(f"{style('qy>')} ")


def _install_repl_readline(qy: Qy) -> None:
    try:
        import readline
    except ImportError:
        return

    history_path = Path.home() / ".qy_history"
    try:
        readline.read_history_file(history_path)
    except OSError:
        pass
    atexit.register(_write_repl_history, readline, history_path)
    readline.set_completer_delims(" \t\n()\"'")
    readline.set_completer(_repl_completer(qy))
    readline.parse_and_bind("tab: complete")


def _write_repl_history(readline_module: Any, history_path: Path) -> None:
    try:
        readline_module.write_history_file(history_path)
    except OSError:
        pass


def _repl_completer(qy: Qy):
    def complete(text: str, state: int) -> str | None:
        matches = _repl_completions(qy, text)
        try:
            return matches[state]
        except IndexError:
            return None

    return complete


def _repl_completions(qy: Qy, text: str) -> list[str]:
    symbols = [symbol.name for symbol in qy.env.bindings()]
    candidates = (*REPL_COMMANDS, *symbols)
    return sorted(candidate for candidate in candidates if candidate.startswith(text))


def _print_repl_help() -> None:
    click.echo("Enter qy expressions to evaluate them in the current session.")
    click.echo(".env          show bound symbols")
    click.echo(".ast <expr>   print the parsed syntax tree")
    click.echo(".fmt <expr>   print canonical qy formatting")
    click.echo(".check <expr> run analyzer diagnostics")
    click.echo(".exit         leave the interpreter")


def _print_environment(qy: Qy) -> None:
    for symbol in sorted(qy.env.bindings(), key=lambda item: item.name):
        click.echo(symbol.name)


def _print_repl_ast(source: str) -> None:
    try:
        click.echo(dump_program(read_raw(source)))
    except ReaderSyntaxError as e:
        secho(f"error: {e}", fg="red", err=True)


def _print_repl_format(source: str) -> None:
    try:
        click.echo(format_source(source), nl=False)
    except ReaderSyntaxError as e:
        secho(f"error: {e}", fg="red", err=True)


def _print_repl_check(source: str) -> None:
    analysis = analyze_source(source)
    if not analysis.diagnostics:
        secho("ok", fg="green")
        return
    for diagnostic in analysis.diagnostics:
        secho(diagnostic.message, fg=diagnostic_color(diagnostic), err=True)


def register(group: click.Group) -> None:
    """将 repl 命令注册到给定的 click group。."""

    @group.command("repl")
    def repl_command() -> None:
        """Start an interactive Qy session."""
        sys.exit(repl(Qy()))
