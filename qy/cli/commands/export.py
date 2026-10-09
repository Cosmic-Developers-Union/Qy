# -*- coding: utf-8 -*-

"""`qy export` 命令入口。."""

from __future__ import annotations

from pathlib import Path

import click

from qy.backend.vm.bytecode import serialize_bytecode_json
from qy.build.artifact import BYTECODE
from qy.build.pipeline import bytecode_artifact
from qy.build.pipeline import compile_source_to_kind
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.cli._common import secho
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.runtime import Qy

# 支持的 LIR dialect。默认 `compat`，与 `qy run` 一致；`abstract-machine` 把
# 语言级 effect 降成 HANDLER_* / CONT_* / EFFECT_* / SLOT_COMPLETE 抽象机指令，
# 供外部 VM 与 verifier 消费（见 tests/test_abstract_machine_vm.py 的差分结论）。
LIR_DIALECTS = ("compat", "abstract-machine")


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
    @click.option(
        "--dialect",
        "dialect",
        type=click.Choice(LIR_DIALECTS),
        default="compat",
        show_default=True,
        help="LIR dialect used to lower the program before emitting bytecode.",
    )
    def export_command(target: str, output: str, dialect: str) -> None:
        """Export bytecode in JSON interchange format for external VMs."""
        qy = Qy()
        source, source_name = read_debug_source(target)
        # 与 `qy/cli/_common.compile_source_to` 一致，只是显式传入
        # `PipelineOptions(lir_dialect=...)`。error_threshold=1：在第一个出错的 pass
        # 后短路（同一 pass 内仍收集全部诊断），避免在已 fail 的 HIR 上继续 lowering
        # 产生 "LIR main function index ... out of range" 这类二次内部错误。
        session = PipelineSession(env=qy.env, source_name=source_name)
        result = compile_source_to_kind(
            source,
            session,
            kind=BYTECODE,
            options=PipelineOptions(lir_dialect=dialect, error_threshold=1),
        )
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
