# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from qy.evaluator import ArgumentEvaluator
from qy.evaluator import Environment
from qy.evaluator import evaluate
from qy.evaluator import standard_environment
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

    def evaluate(self, expression: object) -> object:
        return evaluate(expression, self.env)

    def evaluate_source(self, source: str) -> object:
        return self.evaluate(read_one(source))

    def evaluate_program(self, source: str) -> list[object]:
        return [self.evaluate(form) for form in read(source)]

    def evaluate_file(self, path: str | Path) -> object:
        results = self.evaluate_program(Path(path).read_text(encoding="utf-8"))
        if not results:
            return None
        return results[-1]

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
        argument_evaluator: ArgumentEvaluator | None = None,
    ) -> Callable[..., object]:
        registered = self.env.register_pure(
            name, func, doc=doc, argument_evaluator=argument_evaluator
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
    ) -> Callable[..., object]:
        registered = self.env.register_scope(name, func, doc=doc)
        if func is None:
            return registered
        return func

    def register_control(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
    ) -> Callable[..., object]:
        registered = self.env.register_control(name, func, doc=doc)
        if func is None:
            return registered
        return func

    def register_effect(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
    ) -> Callable[..., object]:
        registered = self.env.register_effect(name, func, doc=doc)
        if func is None:
            return registered
        return func

    def register_meta(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
    ) -> Callable[..., object]:
        registered = self.env.register_meta(name, func, doc=doc)
        if func is None:
            return registered
        return func

    def register_evaluation(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
    ) -> Callable[..., object]:
        return self.register_control(name, func, doc=doc)

    def register_syntax(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
    ) -> Callable[..., object]:
        return self.register_meta(name, func, doc=doc)
