# -*- coding: utf-8 -*-

"""`qy run` 命令入口。."""

from __future__ import annotations

import click

from qy.cli._common import _is_definition_artifact
from qy.cli._common import read_debug_source
from qy.cli._common import secho
from qy.display import format_value
from qy.errors import QyError
from qy.errors import format_qy_error
from qy.runtime import Qy


def register(group: click.Group) -> None:
    """将 run 命令注册到给定的 click group。."""

    @group.command("run")
    @click.argument("path", type=str)
    @click.argument("args", nargs=-1)
    @click.option(
        "--bytecode",
        "as_bytecode",
        is_flag=True,
        default=False,
        help="Treat PATH as JSON bytecode from `qy export` instead of Qy source.",
    )
    def run_command(path: str, args: tuple[str, ...], as_bytecode: bool) -> None:
        """Evaluate a Qy source file. Use '-' for stdin."""
        try:
            qy = Qy()
            if args:
                from qy.ext.interp import set_cli_args

                set_cli_args(qy.env, tuple(args))
            if as_bytecode:
                from pathlib import Path as _Path

                text = (
                    click.get_text_stream("stdin").read()
                    if path == "-"
                    else _Path(path).read_text(encoding="utf-8")
                )
                results = qy.run_bytecode_json(text)
            else:
                source, source_name = read_debug_source(path)
                results = qy.evaluate_program(source, source_name=source_name)
            for value in results:
                if _is_definition_artifact(value):
                    continue
                click.echo(format_value(value))
        except QyError as e:
            secho(format_qy_error(e), fg="red", err=True)
            raise click.exceptions.Exit(1) from e
