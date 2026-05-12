# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from qy.evaluator import ArgumentEvaluator
from qy.evaluator import Environment
from qy.evaluator import evaluate
from qy.evaluator import evaluate_async
from qy.evaluator import evaluate_file_async
from qy.evaluator import evaluate_program_async
from qy.evaluator import standard_environment
from qy.ir import ProgramIR
from qy.ir_vm import evaluate_ir
from qy.ir_vm import evaluate_ir_async
from qy.ir_vm import evaluate_ir_source
from qy.ir_vm import evaluate_ir_source_async
from qy.lowering import lower
from qy.lowering import lower_source
from qy.operator_signature import OperatorSignature
from qy.reader import Form
from qy.reader import read
from qy.reader import read_one

__all__ = ["Qy"]


class Qy:
    def __init__(self, env: Environment | None = None) -> None:
        self.env = env or standard_environment()

    def read(self, source: str) -> list[Form]:
        return read(source)

    def read_one(self, source: str) -> Form:
        return read_one(source)

    def lower(self, forms: list[Form]) -> ProgramIR:
        return lower(forms, self.env)

    def lower_source(self, source: str, *, source_name: str | None = None) -> ProgramIR:
        return lower_source(source, self.env, source_name=source_name)

    def evaluate_ir(self, program: ProgramIR) -> object:
        return evaluate_ir(program, self.env)

    async def evaluate_ir_async(self, program: ProgramIR) -> object:
        return await evaluate_ir_async(program, self.env)

    def evaluate_ir_source(self, source: str, *, source_name: str | None = None) -> object:
        return evaluate_ir_source(source, self.env, source_name=source_name)

    async def evaluate_ir_source_async(
        self, source: str, *, source_name: str | None = None
    ) -> object:
        return await evaluate_ir_source_async(source, self.env, source_name=source_name)

    def evaluate(self, expression: object) -> object:
        return evaluate(expression, self.env)

    async def evaluate_async(self, expression: object) -> object:
        return await evaluate_async(expression, self.env)

    def evaluate_source(self, source: str, *, source_name: str | None = None) -> object:
        return self.evaluate(read_one(source, source_name=source_name))

    async def evaluate_source_async(self, source: str, *, source_name: str | None = None) -> object:
        return await self.evaluate_async(read_one(source, source_name=source_name))

    def evaluate_program(self, source: str, *, source_name: str | None = None) -> list[object]:
        return [self.evaluate(form) for form in read(source, source_name=source_name)]

    async def evaluate_program_async(
        self, source: str, *, source_name: str | None = None
    ) -> list[object]:
        return await evaluate_program_async(source, self.env, source_name=source_name)

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
        return await evaluate_file_async(path, self.env)

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
