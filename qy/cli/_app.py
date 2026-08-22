# -*- coding: utf-8 -*-

"""CLI 应用构建与根 group 配置."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click


class QyGroup(click.Group):
    """Click group with a fallback intent to re-route ``qy FILE [ARGS]`` to ``qy run FILE [ARGS]``.

    When click fails to resolve the first positional argument as a subcommand
    **and** that argument names an existing file in the current working
    directory, the call is forwarded to the ``run`` subcommand with the same
    remaining arguments. This is the documented shortcut ``qy FILE evaluates
    FILE``.
    """

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            if args and not args[0].startswith("-") and Path(args[0]).is_file():
                command = self.get_command(ctx, "run")
                if command is not None:
                    return "run", command, args
            raise


def build_cli() -> click.Group:
    """Construct the top-level click group and register all subcommands."""

    @click.group(
        name="qy",
        cls=QyGroup,
        help="Qy command line tools.",
        epilog="Shortcut: qy FILE evaluates FILE.",
        invoke_without_command=True,
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    @click.option(
        "--no-color",
        is_flag=True,
        default=False,
        help="Disable ANSI color output in errors and status messages.",
    )
    @click.pass_context
    def qy_cli(ctx: click.Context, no_color: bool) -> None:
        if no_color:
            os.environ["NO_COLOR"] = "1"
        if ctx.invoked_subcommand is None:
            from qy.cli.commands.repl import repl as run_repl
            from qy.runtime import Qy

            sys.exit(run_repl(Qy()))

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

    register_run(qy_cli)
    register_repl(qy_cli)
    register_pipeline_commands(qy_cli)
    register_ast(qy_cli)
    register_operators(qy_cli)
    register_completion(qy_cli)
    register_export(qy_cli)
    register_llvm(qy_cli)
    fmt_cmd.register(qy_cli)
    check_cmd.register(qy_cli)
    lsp_cmd.register(qy_cli)
    qy_cli.add_command(create_pkg_app(), name="pkg")

    return qy_cli
