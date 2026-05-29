# -*- coding: utf-8 -*-

"""`qy ast` 命令入口。."""

from pathlib import Path
from typing import Annotated
from typing import Any

import typer

from qy.build.pipeline import core_ast_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.runtime import Qy
from qy.tools.fmt import dump_program


def register(app: Any) -> None:
    """将 ast 命令注册到给定的 typer 应用。."""

    @app.command("ast")
    def ast_command(
        path: Annotated[Path, typer.Argument(help="Qy source file to inspect.")],
        raw: Annotated[
            bool,
            typer.Option("--raw", help="Show raw AST without surface dialect expansion."),
        ] = False,
        expand: Annotated[
            bool,
            typer.Option("--expand", help="Show AST after macro expansion."),
        ] = False,
        cst: Annotated[
            bool,
            typer.Option("--cst", help="Show concrete syntax tree (preserves trivia)."),
        ] = False,
    ) -> None:
        source = path.read_text(encoding="utf-8")
        if cst:
            from qy.frontend.reader import parse_cst
            from qy.tools.fmt import dump_cst

            program = parse_cst(source, source_name=str(path))
            typer.echo(dump_cst(program))
        elif raw:
            from qy.frontend.reader import read_raw

            forms = read_raw(source)
            typer.echo(dump_program(forms))
        elif expand:
            qy = Qy()
            result = compile_source_to(qy, source, kind="core-ast", source_name=str(path))
            has_errors = print_debug_diagnostics(str(path), result.diagnostics)
            try:
                program = core_ast_artifact(result)
            except TypeError:
                if has_errors:
                    raise typer.Exit(1) from None
                return
            if program.forms:
                typer.echo(dump_program(program.forms), nl=False)
            if has_errors:
                raise typer.Exit(1)
        else:
            from qy.frontend.reader import read

            forms = read(source)
            typer.echo(dump_program(forms))
