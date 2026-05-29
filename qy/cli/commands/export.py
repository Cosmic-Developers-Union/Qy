# -*- coding: utf-8 -*-

"""`qy export` 命令入口。."""

from pathlib import Path
from typing import Annotated
from typing import Any

import typer

from qy.backend.vm.bytecode import serialize_bytecode_json
from qy.build.pipeline import bytecode_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.runtime import Qy


def register(app: Any) -> None:
    """将 export 命令注册到给定的 typer 应用。."""

    @app.command("export")
    def export_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to compile and export, or - to read from stdin."),
        ],
        output: Annotated[
            str,
            typer.Option("--output", "-o", help="Output file path. Defaults to stdout."),
        ] = "-",
    ) -> None:
        """Export bytecode in JSON interchange format for external VMs."""
        qy = Qy()
        source, source_name = read_debug_source(target)
        result = compile_source_to(qy, source, kind="bytecode", source_name=source_name)
        has_errors = print_debug_diagnostics(source_name, result.diagnostics)
        try:
            bytecode = bytecode_artifact(result)
        except TypeError:
            if has_errors:
                raise typer.Exit(1) from None
            return
        json_text = serialize_bytecode_json(bytecode, env=qy.env)
        if output == "-":
            typer.echo(json_text, nl=False)
        else:
            Path(output).write_text(json_text, encoding="utf-8")
            typer.secho(f"exported to {output}", fg=typer.colors.GREEN, err=True)
        if has_errors:
            raise typer.Exit(1)
