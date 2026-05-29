# -*- coding: utf-8 -*-

"""`qy llvm` 命令入口。."""

from typing import Annotated
from typing import Any

import typer

from qy.build.pipeline import lir_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.runtime import Qy


def register(app: Any) -> None:
    """将 llvm 命令注册到给定的 typer 应用。."""

    @app.command("llvm")
    def llvm_command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to compile to LLVM IR, or - to read from stdin."),
        ],
    ) -> None:
        from qy.backend.llvm.emit import emit as emit_llvm_module

        qy = Qy()
        source, source_name = read_debug_source(target)
        result = compile_source_to(qy, source, kind="lir", source_name=source_name)
        has_errors = print_debug_diagnostics(source_name, result.diagnostics)
        try:
            lir = lir_artifact(result)
        except TypeError:
            if has_errors:
                raise typer.Exit(1) from None
            return
        if lir.ok:
            ll_text = emit_llvm_module(lir)
            typer.echo(ll_text, nl=False)
        if has_errors:
            raise typer.Exit(1)
