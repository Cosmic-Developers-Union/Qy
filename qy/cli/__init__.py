# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from typing import Any

from qy.cli._common import CLI_COMMANDS as CLI_COMMANDS
from qy.cli._common import REPL_COMMANDS as REPL_COMMANDS

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
        from qy.cli.commands.repl import repl
        from qy.runtime import Qy

        raise typer.Exit(repl(Qy()))

    from qy.cli._pipeline import register_pipeline_commands
    from qy.cli.commands import check as check_cmd
    from qy.cli.commands import fmt as fmt_cmd
    from qy.cli.commands import lsp as lsp_cmd
    from qy.cli.commands.ast import register as register_ast
    from qy.cli.commands.completion import register as register_completion
    from qy.cli.commands.export import register as register_export
    from qy.cli.commands.llvm import register as register_llvm
    from qy.cli.commands.operators import register as register_operators
    from qy.cli.commands.pkg import create_pkg_app
    from qy.cli.commands.repl import register as register_repl
    from qy.cli.commands.run import register as register_run

    register_run(app)
    register_repl(app)
    register_pipeline_commands(app)
    register_ast(app)
    register_operators(app)
    register_completion(app)
    register_export(app)
    register_llvm(app)
    fmt_cmd.register(app)
    check_cmd.register(app)
    lsp_cmd.register(app)
    app.add_typer(create_pkg_app(), name="pkg")

    return app


# Re-export for external consumers (tests, benchmark CLI, etc.)
def _repl_completions(qy: Any, text: str) -> list[str]:
    from qy.cli.commands.repl import _repl_completions as _impl

    return _impl(qy, text)
