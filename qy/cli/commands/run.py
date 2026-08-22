# -*- coding: utf-8 -*-

"""`qy run` 命令入口。."""

from __future__ import annotations

from pathlib import Path

import click

from qy.cli._common import _is_definition_artifact
from qy.cli._common import secho
from qy.display import format_value
from qy.errors import QyError
from qy.errors import format_qy_error
from qy.runtime import Qy


def register(group: click.Group) -> None:
    """将 run 命令注册到给定的 click group。."""

    @group.command("run")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.argument("args", nargs=-1)
    def run_command(path: Path, args: tuple[str, ...]) -> None:
        """Evaluate a Qy source file."""
        try:
            qy = Qy()
            if args:
                from qy.symbol_space.testhost import set_cli_args

                set_cli_args(qy.env, tuple(args))
            source = path.read_text(encoding="utf-8")
            results = qy.evaluate_program(source, source_name=str(path))
            for value in results:
                if _is_definition_artifact(value):
                    continue
                click.echo(format_value(value))
        except QyError as e:
            secho(format_qy_error(e), fg="red", err=True)
            raise click.exceptions.Exit(1) from e
