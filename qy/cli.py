# coding: utf-8

import sys
from pathlib import Path
from typing import Annotated
from typing import Any
from typing import cast

from qy.analyzer import Diagnostic
from qy.analyzer import analyze_source
from qy.errors import QyError
from qy.errors import format_qy_error
from qy.formatter import dump_program
from qy.formatter import format_source
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import read
from qy.reader import write_tuple
from qy.runtime import Qy

INSTALL_CLI_MESSAGE = (
    "Qy CLI requires the optional cli dependency. Install with: pip install 'QyLang[cli]'"
)
INSTALL_LSP_MESSAGE = (
    "Qy LSP requires the optional lsp dependency. Install with: pip install 'QyLang[lsp]'"
)


def main() -> int:
    try:
        app = create_app()
    except ModuleNotFoundError as e:
        if e.name == "typer":
            print(INSTALL_CLI_MESSAGE, file=sys.stderr)
            return 2
        raise
    app()
    return 0


def create_app() -> Any:
    import click
    import typer
    from typer.core import TyperGroup

    class QyGroup(TyperGroup):
        def resolve_command(
            self, ctx: click.Context, args: list[str]
        ) -> tuple[str | None, click.Command | None, list[str]]:
            try:
                return super().resolve_command(ctx, args)
            except click.UsageError:
                if args and not args[0].startswith("-") and Path(args[0]).is_file():
                    command = self.get_command(ctx, "run")
                    return "run", command, args
                raise

    app = typer.Typer(
        add_completion=False,
        cls=QyGroup,
        epilog="Shortcut: qy FILE evaluates FILE.",
        help="Qy command line tools.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @app.callback()
    def root(ctx: typer.Context) -> None:
        if ctx.invoked_subcommand is not None:
            return
        raise typer.Exit(repl(Qy()))

    @app.command("run")
    def run_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to evaluate.")],
    ) -> None:
        try:
            typer.echo(format_value(Qy().evaluate_file(path)))
        except QyError as e:
            typer.secho(format_qy_error(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e

    @app.command("repl")
    def repl_command() -> None:
        raise typer.Exit(repl(Qy()))

    @app.command("fmt")
    def format_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to format.")],
        write: Annotated[
            bool,
            typer.Option("--write", "-w", help="Rewrite the file in place."),
        ] = False,
    ) -> None:
        formatted = format_source(path.read_text(encoding="utf-8"))
        if write:
            path.write_text(formatted, encoding="utf-8")
            typer.secho(f"formatted {path}", fg=typer.colors.GREEN)
            return
        typer.echo(formatted, nl=False)

    @app.command("ast")
    def ast_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to inspect.")],
    ) -> None:
        typer.echo(dump_program(read(path.read_text(encoding="utf-8"))))

    @app.command("check")
    def check_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to check.")],
    ) -> None:
        _check_path(path)

    @app.command("typecheck")
    def typecheck_command(path: Annotated[Path, typer.Argument(help="Alias for check.")]) -> None:
        _check_path(path)

    @app.command("lsp")
    def lsp_command() -> None:
        try:
            from qy.lsp import main as lsp_main
        except ModuleNotFoundError as e:
            if e.name in {"pygls", "lsprotocol"}:
                typer.secho(INSTALL_LSP_MESSAGE, fg=typer.colors.RED, err=True)
                raise typer.Exit(2) from e
            raise
        raise typer.Exit(lsp_main())

    return app


def repl(qy: Qy) -> int:
    import typer

    typer.secho("Qy interactive interpreter", fg=typer.colors.GREEN, bold=True)
    typer.echo("Commands: .help .env .ast <expr> .fmt <expr> .check <expr> .exit")
    while True:
        try:
            source = typer.prompt(typer.style("qy>", fg=typer.colors.BLUE), prompt_suffix=" ")
        except (EOFError, KeyboardInterrupt):
            typer.echo()
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
                typer.echo(format_value(qy.evaluate(form)))
        except QyError as e:
            typer.secho(format_qy_error(e), fg=typer.colors.RED, err=True)


def format_value(value: object) -> str:
    if isinstance(value, Symbol | tuple | int | float | bool) or value is None:
        try:
            return write_tuple(cast(TupleForm, value))
        except TypeError:
            pass
    return repr(value)


def _check_path(path: Path) -> None:
    import typer

    analysis = analyze_source(path.read_text(encoding="utf-8"))
    for diagnostic in analysis.diagnostics:
        typer.secho(
            _format_diagnostic(path, diagnostic), fg=_diagnostic_color(diagnostic), err=True
        )
    if not analysis.ok:
        raise typer.Exit(1)
    typer.secho(f"{path}: ok", fg=typer.colors.GREEN)


def _format_diagnostic(path: Path, diagnostic: Diagnostic) -> str:
    location = str(path)
    if diagnostic.line is not None and diagnostic.column is not None:
        location = f"{location}:{diagnostic.line}:{diagnostic.column}"
    return f"{location}: {diagnostic.severity}: {diagnostic.message}"


def _diagnostic_color(diagnostic: Diagnostic) -> str:
    import typer

    if diagnostic.severity == "warning":
        return typer.colors.YELLOW
    if diagnostic.severity == "hint":
        return typer.colors.BLUE
    return typer.colors.RED


def _print_repl_help() -> None:
    import typer

    typer.echo("Enter qy expressions to evaluate them in the current session.")
    typer.echo(".env          show bound symbols")
    typer.echo(".ast <expr>   print the parsed syntax tree")
    typer.echo(".fmt <expr>   print canonical qy formatting")
    typer.echo(".check <expr> run analyzer diagnostics")
    typer.echo(".exit         leave the interpreter")


def _print_environment(qy: Qy) -> None:
    import typer

    for symbol in sorted(qy.env.bindings(), key=lambda item: item.name):
        typer.echo(symbol.name)


def _print_repl_ast(source: str) -> None:
    import typer

    try:
        typer.echo(dump_program(read(source)))
    except ReaderSyntaxError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)


def _print_repl_format(source: str) -> None:
    import typer

    try:
        typer.echo(format_source(source), nl=False)
    except ReaderSyntaxError as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)


def _print_repl_check(source: str) -> None:
    import typer

    analysis = analyze_source(source)
    if not analysis.diagnostics:
        typer.secho("ok", fg=typer.colors.GREEN)
        return
    for diagnostic in analysis.diagnostics:
        typer.secho(diagnostic.message, fg=_diagnostic_color(diagnostic), err=True)


if __name__ == "__main__":
    raise SystemExit(main())
