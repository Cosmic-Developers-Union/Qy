# -*- coding: utf-8 -*-

"""`qy export` 命令入口。."""

from __future__ import annotations

from pathlib import Path

import click

from qy.backend.vm.bytecode import serialize_bytecode_json
from qy.build.pipeline import bytecode_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.cli._common import secho
from qy.runtime import Qy


def register(group: click.Group) -> None:
    """将 export 命令注册到给定的 click group。."""

    @group.command("export")
    @click.argument("target")
    @click.option(
        "--output",
        "-o",
        default="-",
        help="Output file path. Defaults to stdout.",
    )
    def export_command(target: str, output: str) -> None:
        """Export bytecode in JSON interchange format for external VMs."""
        qy = Qy()
        source, source_name = read_debug_source(target)
        result = compile_source_to(qy, source, kind="bytecode", source_name=source_name)
        has_errors = print_debug_diagnostics(source_name, result.diagnostics)
        try:
            bytecode = bytecode_artifact(result)
        except TypeError:
            if has_errors:
                raise click.exceptions.Exit(1) from None
            return
        json_text = serialize_bytecode_json(bytecode, env=qy.env)
        if output == "-":
            click.echo(json_text, nl=False)
        else:
            Path(output).write_text(json_text, encoding="utf-8")
            secho(f"exported to {output}", fg="green", err=True)
        if has_errors:
            raise click.exceptions.Exit(1)
