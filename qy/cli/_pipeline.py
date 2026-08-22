# -*- coding: utf-8 -*-

"""Pipeline 调试命令 (expand/hir/mir/lir/bytecode) 的公共注册。."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import click

from qy.backend.vm.bytecode import dump_bytecode
from qy.build.pipeline import bytecode_artifact
from qy.build.pipeline import core_ast_artifact
from qy.build.pipeline import hir_artifact
from qy.build.pipeline import lir_artifact
from qy.build.pipeline import mir_artifact
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.ir import dump_ir
from qy.ir.lir import dump_lir
from qy.ir.mir import dump_mir
from qy.runtime import Qy
from qy.tools.fmt import dump_program

_PIPELINE_COMMANDS: dict[str, dict[str, Any]] = {
    "expand": {
        "kind": "core-ast",
        "help": "Expand a Qy source file to core AST. Use '-' for stdin.",
        "artifact_fn": core_ast_artifact,
        "dump_fn": lambda p: dump_program(p.forms) if p.forms else "",
    },
    "hir": {
        "kind": "hir",
        "help": "Lower a Qy source file to HIR. Use '-' for stdin.",
        "artifact_fn": hir_artifact,
        "dump_fn": dump_ir,
    },
    "mir": {
        "kind": "mir",
        "help": "Lower a Qy source file to MIR. Use '-' for stdin.",
        "artifact_fn": mir_artifact,
        "dump_fn": dump_mir,
    },
    "lir": {
        "kind": "lir",
        "help": "Lower a Qy source file to LIR. Use '-' for stdin.",
        "artifact_fn": lir_artifact,
        "dump_fn": dump_lir,
    },
    "bytecode": {
        "kind": "bytecode",
        "help": "Compile a Qy source file to bytecode. Use '-' for stdin.",
        "artifact_fn": bytecode_artifact,
        "dump_fn": dump_bytecode,
    },
}


def _make_pipeline_command(
    kind: str,
    artifact_fn: Callable[..., Any],
    dump_fn: Callable[..., str],
) -> click.Command:
    @click.command(context_settings={"help_option_names": ["-h", "--help"]})
    @click.argument("target")
    def command(target: str) -> None:
        qy = Qy()
        source, source_name = read_debug_source(target)
        result = compile_source_to(qy, source, kind=kind, source_name=source_name)
        has_errors = print_debug_diagnostics(source_name, result.diagnostics)
        try:
            artifact = artifact_fn(result)
        except TypeError:
            if has_errors:
                raise click.exceptions.Exit(1) from None
            return
        click.echo(dump_fn(artifact), nl=False)
        if has_errors:
            raise click.exceptions.Exit(1)

    return command


def register_pipeline_commands(group: click.Group) -> None:
    """注册 expand/hir/mir/lir/bytecode 五个 pipeline 调试命令。."""
    for name, cfg in _PIPELINE_COMMANDS.items():
        cmd = _make_pipeline_command(cfg["kind"], cfg["artifact_fn"], cfg["dump_fn"])
        cmd.help = cfg["help"]
        group.add_command(cmd, name=name)
