# -*- coding: utf-8 -*-

"""`qy wasm` 命令入口。.

目标：把 Qy 源码降到 WebAssembly text（WAT），供 ``wat2wasm`` 汇编后由
Node 的 WebAssembly 引擎执行（宿主 runtime 见
``qy/resources/wasm/runtime.js``）。

禁止：不得在 CLI 里定义后端语义。
"""

from __future__ import annotations

import click

from qy.build.pipeline import lir_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.cli._common import secho
from qy.runtime import Qy


def register(group: click.Group) -> None:
    """将 wasm 命令注册到给定的 click group。."""

    @group.command("wasm")
    @click.argument("target")
    def wasm_command(target: str) -> None:
        """Compile a Qy source file to WebAssembly text (WAT)."""
        from qy.backend.wasm.emit import WasmUnsupportedError
        from qy.backend.wasm.emit import emit as emit_wasm_module

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
            try:
                wat_text = emit_wasm_module(lir)
            except WasmUnsupportedError as error:
                secho(f"{source_name}: error: {error}", fg="red", err=True)
                raise click.exceptions.Exit(1) from None
            click.echo(wat_text, nl=False)
        if has_errors:
            raise click.exceptions.Exit(1)
