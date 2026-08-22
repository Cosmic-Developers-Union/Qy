# -*- coding: utf-8 -*-

"""`qy ast` 命令入口。."""

from __future__ import annotations

from pathlib import Path

import click

from qy.build.pipeline import core_ast_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.runtime import Qy
from qy.tools.fmt import dump_program


def register(group: click.Group) -> None:
    """将 ast 命令注册到给定的 click group。."""

    @group.command("ast")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option(
        "--raw",
        is_flag=True,
        help="Show raw AST without surface dialect expansion.",
    )
    @click.option(
        "--expand",
        is_flag=True,
        help="Show AST after macro expansion.",
    )
    @click.option(
        "--cst",
        is_flag=True,
        help="Show concrete syntax tree (preserves trivia).",
    )
    def ast_command(path: Path, raw: bool, expand: bool, cst: bool) -> None:
        """Print the parsed syntax tree of a Qy source file."""
        source = path.read_text(encoding="utf-8")
        if cst:
            from qy.frontend.reader import parse_cst
            from qy.tools.fmt import dump_cst

            program = parse_cst(source, source_name=str(path))
            click.echo(dump_cst(program))
        elif raw:
            from qy.frontend.reader import read_raw

            forms = read_raw(source)
            click.echo(dump_program(forms))
        elif expand:
            qy = Qy()
            result = compile_source_to(qy, source, kind="core-ast", source_name=str(path))
            has_errors = print_debug_diagnostics(str(path), result.diagnostics)
            try:
                program = core_ast_artifact(result)
            except TypeError:
                if has_errors:
                    raise click.exceptions.Exit(1) from None
                return
            if program.forms:
                click.echo(dump_program(program.forms), nl=False)
            if has_errors:
                raise click.exceptions.Exit(1)
        else:
            from qy.frontend.reader import read

            forms = read(source)
            click.echo(dump_program(forms))
