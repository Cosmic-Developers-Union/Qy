# -*- coding: utf-8 -*-

"""`qy llvm` 命令入口。."""

from __future__ import annotations

import click

from qy.build.pipeline import lir_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.runtime import Qy


def register(group: click.Group) -> None:
    """将 llvm 命令注册到给定的 click group。."""

    @group.command("llvm")
    @click.argument("target")
    def llvm_command(target: str) -> None:
        """Compile a Qy source file to LLVM IR (use '-' for stdin)."""
        from qy.backend.llvm.emit import emit as emit_llvm_module

        qy = Qy()
        source, source_name = read_debug_source(target)
        result = compile_source_to(qy, source, kind="lir", source_name=source_name)
        has_errors = print_debug_diagnostics(source_name, result.diagnostics)
        try:
            lir = lir_artifact(result)
        except TypeError:
            if has_errors:
                raise click.exceptions.Exit(1) from None
            return
        if lir.ok:
            ll_text = emit_llvm_module(lir)
            click.echo(ll_text, nl=False)
        if has_errors:
            raise click.exceptions.Exit(1)
