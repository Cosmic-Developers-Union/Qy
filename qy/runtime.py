# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from qy.async_runtime import run_async
from qy.bytecode import BytecodeProgram
from qy.bytecode_compiler import compile_bytecode
from qy.bytecode_compiler import compile_mir_bytecode
from qy.environment import ChainFrame
from qy.environment import Environment
from qy.environment import standard_environment
from qy.ir import ProgramIR
from qy.ir.mir import MIRProgram
from qy.macroexpand import MacroExpansion
from qy.macroexpand import MacroExpansionOptions
from qy.macroexpand import macroexpand
from qy.macroexpand import macroexpand_async
from qy.macroexpand import macroexpand_source
from qy.macroexpand import macroexpand_source_async
from qy.operator_signature import OperatorSignature
from qy.operators import ArgumentEvaluator
from qy.passes.lower_hir import lower
from qy.passes.lower_hir import lower_source
from qy.passes.lower_mir import lower_mir
from qy.reader import Form
from qy.reader import read
from qy.reader import read_one
from qy.register_vm import RegisterVirtualMachine
from qy.register_vm import evaluate_bytecode
from qy.register_vm import evaluate_bytecode_async
from qy.register_vm import evaluate_bytecode_source
from qy.register_vm import evaluate_bytecode_source_async

__all__ = ["Qy"]


class Qy:
    def __init__(self, env: Environment | None = None) -> None:
        self.env = env or standard_environment()

    @property
    def pre_symbol_space_chain(self) -> tuple[ChainFrame, ...]:
        return self.env.pre_symbol_space_chain()

    def read(self, source: str) -> list[Form]:
        return read(source)

    def read_one(self, source: str) -> Form:
        return read_one(source)

    def lower(self, forms: list[Form]) -> ProgramIR:
        return lower(forms, self.env)

    def lower_source(self, source: str, *, source_name: str | None = None) -> ProgramIR:
        return lower_source(source, self.env, source_name=source_name)

    def macroexpand(
        self,
        forms: list[Form],
        *,
        options: MacroExpansionOptions | None = None,
    ) -> MacroExpansion:
        return macroexpand(forms, self.env, options=options)

    async def macroexpand_async(
        self,
        forms: list[Form],
        *,
        options: MacroExpansionOptions | None = None,
    ) -> MacroExpansion:
        return await macroexpand_async(forms, self.env, options=options)

    def macroexpand_source(
        self,
        source: str,
        *,
        source_name: str | None = None,
        options: MacroExpansionOptions | None = None,
    ) -> MacroExpansion:
        return macroexpand_source(source, self.env, source_name=source_name, options=options)

    async def macroexpand_source_async(
        self,
        source: str,
        *,
        source_name: str | None = None,
        options: MacroExpansionOptions | None = None,
    ) -> MacroExpansion:
        return await macroexpand_source_async(
            source,
            self.env,
            source_name=source_name,
            options=options,
        )

    def lower_mir(self, program: ProgramIR) -> MIRProgram:
        return lower_mir(program)

    def compile_bytecode(self, program: ProgramIR) -> BytecodeProgram:
        return compile_bytecode(program)

    def compile_mir_bytecode(self, program: MIRProgram) -> BytecodeProgram:
        return compile_mir_bytecode(program)

    def evaluate_bytecode(self, program: BytecodeProgram) -> object:
        return evaluate_bytecode(program, self.env)

    async def evaluate_bytecode_async(self, program: BytecodeProgram) -> object:
        return await evaluate_bytecode_async(program, self.env)

    def evaluate_bytecode_source(self, source: str, *, source_name: str | None = None) -> object:
        return evaluate_bytecode_source(source, self.env, source_name=source_name)

    async def evaluate_bytecode_source_async(
        self, source: str, *, source_name: str | None = None
    ) -> object:
        return await evaluate_bytecode_source_async(source, self.env, source_name=source_name)

    def evaluate(self, expression: object) -> object:
        expansion = macroexpand([cast(Form, expression)], self.env)
        program = lower(expansion.forms, self.env)
        return self.evaluate_bytecode(compile_bytecode(program))

    async def evaluate_async(self, expression: object) -> object:
        expansion = await macroexpand_async([cast(Form, expression)], self.env)
        program = lower(expansion.forms, self.env)
        return await self.evaluate_bytecode_async(compile_bytecode(program))

    def evaluate_source(self, source: str, *, source_name: str | None = None) -> object:
        return self.evaluate_bytecode_source(source, source_name=source_name)

    async def evaluate_source_async(self, source: str, *, source_name: str | None = None) -> object:
        return await self.evaluate_bytecode_source_async(source, source_name=source_name)

    def evaluate_program(self, source: str, *, source_name: str | None = None) -> list[object]:
        expansion = macroexpand(read(source, source_name=source_name), self.env)
        program = lower(expansion.forms, self.env)
        bytecode = compile_bytecode(program)
        return cast(
            list[object],
            run_async(RegisterVirtualMachine(bytecode, self.env).evaluate_program()),
        )

    async def evaluate_program_async(
        self, source: str, *, source_name: str | None = None
    ) -> list[object]:
        expansion = await macroexpand_async(read(source, source_name=source_name), self.env)
        program = lower(expansion.forms, self.env)
        return await RegisterVirtualMachine(
            compile_bytecode(program),
            self.env,
        ).evaluate_program()

    def evaluate_file(self, path: str | Path) -> object:
        path = Path(path)
        results = self.evaluate_program(
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        if not results:
            return None
        return results[-1]

    async def evaluate_file_async(self, path: str | Path) -> object:
        path = Path(path)
        results = await self.evaluate_program_async(
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        return None if not results else results[-1]

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
        argument_evaluator: ArgumentEvaluator | None = None,
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_pure(
            name,
            func,
            doc=doc,
            argument_evaluator=argument_evaluator,
            signature=signature,
        )
        if func is None:
            return registered
        return func

    def register_scope(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_scope(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_control(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_control(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_effect(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_effect(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_meta(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_meta(name, func, doc=doc, signature=signature)
        if func is None:
            return registered
        return func

    def register_evaluation(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        return self.register_control(name, func, doc=doc, signature=signature)

    def register_syntax(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> Callable[..., object]:
        return self.register_meta(name, func, doc=doc, signature=signature)
