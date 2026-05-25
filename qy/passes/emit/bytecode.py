# coding: utf-8
"""``emit.bytecode`` —— LIR → ``BytecodeProgram``.

包装 ``qy.backend.vm.compiler.compile_lir_bytecode``，把 LIR 编码为 register VM
可执行的 bytecode 程序。
"""

from __future__ import annotations

from typing import cast

from qy.backend.vm.compiler import compile_lir_bytecode
from qy.ir.lir import LIRProgram
from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult

__all__ = ["EmitBytecodePass"]


class EmitBytecodePass(Pass):
    input_kind = "lir"
    output_kind = "bytecode"

    def __init__(self) -> None:
        super().__init__("emit.bytecode")

    def run(self, context: PassContext) -> PassResult:
        program = cast(LIRProgram, context.input_artifact)
        bytecode = compile_lir_bytecode(program)
        upstream_ids = {id(d) for d in program.diagnostics}
        new_diagnostics = tuple(d for d in bytecode.diagnostics if id(d) not in upstream_ids)
        return PassResult(
            success=True,
            artifact=bytecode,
            artifact_kind=self.output_kind,
            diagnostics=new_diagnostics,
        )
