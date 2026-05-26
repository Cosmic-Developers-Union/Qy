# -*- coding: utf-8 -*-

"""`qy run` 命令入口。."""

from pathlib import Path
from typing import Annotated
from typing import Any

import typer

from qy.cli._common import _is_definition_artifact
from qy.display import format_value
from qy.errors import QyError
from qy.errors import format_qy_error
from qy.runtime import Qy


def register(app: Any) -> None:
    """将 run 命令注册到给定的 typer 应用。."""

    @app.command("run")
    def run_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to evaluate.")],
        args: Annotated[
            list[str] | None,
            typer.Argument(help="Arguments passed through to the Qy runtime program."),
        ] = None,
    ) -> None:
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
                typer.echo(format_value(value))
        except QyError as e:
            typer.secho(format_qy_error(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from e
