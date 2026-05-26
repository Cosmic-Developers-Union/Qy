# -*- coding: utf-8 -*-

"""Pipeline 调试命令 (expand/hir/mir/lir/bytecode) 的公共注册。."""

from typing import Annotated
from typing import Any

import typer

from qy.backend.vm.bytecode import dump_bytecode
from qy.cli._common import compile_source_to
from qy.cli._common import print_debug_diagnostics
from qy.cli._common import read_debug_source
from qy.ir import dump_ir
from qy.ir.lir import dump_lir
from qy.ir.mir import dump_mir
from qy.passes.build import bytecode_artifact
from qy.passes.build import core_ast_artifact
from qy.passes.build import hir_artifact
from qy.passes.build import lir_artifact
from qy.passes.build import mir_artifact
from qy.runtime import Qy
from qy.tools.fmt import dump_program

_PIPELINE_COMMANDS: dict[str, dict[str, Any]] = {
    "expand": {
        "kind": "core-ast",
        "help": "Qy source file to expand, or - to read from stdin.",
        "artifact_fn": core_ast_artifact,
        "dump_fn": lambda p: dump_program(p.forms) if p.forms else "",
    },
    "hir": {
        "kind": "hir",
        "help": "Qy source file to lower, or - to read from stdin.",
        "artifact_fn": hir_artifact,
        "dump_fn": dump_ir,
    },
    "mir": {
        "kind": "mir",
        "help": "Qy source file to lower into MIR, or - to read from stdin.",
        "artifact_fn": mir_artifact,
        "dump_fn": dump_mir,
    },
    "lir": {
        "kind": "lir",
        "help": "Qy source file to lower into LIR, or - to read from stdin.",
        "artifact_fn": lir_artifact,
        "dump_fn": dump_lir,
    },
    "bytecode": {
        "kind": "bytecode",
        "help": "Qy source file to compile, or - to read from stdin.",
        "artifact_fn": bytecode_artifact,
        "dump_fn": dump_bytecode,
    },
}


def _make_pipeline_command(
    kind: str,
    artifact_fn: Any,
    dump_fn: Any,
) -> Any:
    def command(
        target: Annotated[
            str,
            typer.Argument(help="Qy source file to inspect, or - to read from stdin."),
        ],
    ) -> None:
        qy = Qy()
        source, source_name = read_debug_source(target)
        result = compile_source_to(qy, source, kind=kind, source_name=source_name)
        has_errors = print_debug_diagnostics(source_name, result.diagnostics)
        try:
            artifact = artifact_fn(result)
        except TypeError:
            if has_errors:
                raise typer.Exit(1) from None
            return
        typer.echo(dump_fn(artifact), nl=False)
        if has_errors:
            raise typer.Exit(1)

    return command


def register_pipeline_commands(app: Any) -> None:
    """注册 expand/hir/mir/lir/bytecode 五个 pipeline 调试命令。."""
    for name, cfg in _PIPELINE_COMMANDS.items():
        fn = _make_pipeline_command(cfg["kind"], cfg["artifact_fn"], cfg["dump_fn"])
        fn.__name__ = name
        app.command(name)(fn)
