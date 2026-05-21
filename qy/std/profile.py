# coding: utf-8

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.macro import MacroDefinition
from qy.sem.runtime import EffectDefinition
from qy.std import STANDARD_PROFILE_MODULES
from qy.std import load_module

__all__ = [
    "OperatorDoc",
    "OperatorModuleDoc",
    "collect_supported_operators",
    "format_operator_docs",
]


@dataclass(frozen=True, slots=True)
class OperatorDoc:
    name: str
    kind: str
    kind_label: str
    doc: str


@dataclass(frozen=True, slots=True)
class OperatorModuleDoc:
    module_name: str
    title: str
    operators: tuple[OperatorDoc, ...]


_KIND_LABELS = {
    "pure": "纯算子",
    "scope": "作用域算子",
    "control": "控制算子",
    "effect": "Effect 算子",
    "meta": "元算子",
    "effect-definition": "Effect 定义",
}


def collect_supported_operators(
    modules: Iterable[str] = STANDARD_PROFILE_MODULES,
) -> tuple[OperatorModuleDoc, ...]:
    groups: list[OperatorModuleDoc] = []
    for module_name in modules:
        module = load_module(module_name)
        operators = tuple(
            sorted(
                (
                    _operator_doc(symbol.name, value)
                    for symbol, value in module.exports.items()
                    if _operator_kind(value) is not None
                ),
                key=lambda item: item.name,
            )
        )
        if operators:
            groups.append(
                OperatorModuleDoc(
                    module_name=module.name,
                    title=_module_title(module.name),
                    operators=operators,
                )
            )
    return tuple(groups)


def format_operator_docs(groups: Iterable[OperatorModuleDoc] | None = None) -> str:
    if groups is None:
        groups = collect_supported_operators()
    groups = tuple(groups)
    lines = ["# Qy 支持的算子", ""]
    for group in groups:
        lines.append(f"## {group.title}")
        lines.append("")
        lines.append(f"模块：`{group.module_name}`")
        lines.append("")
        for operator in group.operators:
            line = f"- `{operator.name}` - {operator.kind_label}"
            if operator.doc:
                line = f"{line}：{operator.doc}"
            lines.append(line)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _operator_doc(name: str, value: object) -> OperatorDoc:
    kind = _operator_kind(value)
    assert kind is not None
    return OperatorDoc(
        name=name,
        kind=kind,
        kind_label=_KIND_LABELS[kind],
        doc=getattr(value, "doc", ""),
    )


def _operator_kind(value: object) -> str | None:
    if isinstance(value, PureOperator):
        return "pure"
    if isinstance(value, ScopeOperator):
        return "scope"
    if isinstance(value, ControlOperator):
        return "control"
    if isinstance(value, EffectOperator):
        return "effect"
    if isinstance(value, MetaOperator | MacroDefinition):
        return "meta"
    if isinstance(value, EffectDefinition):
        return "effect-definition"
    return None


def _module_title(module_name: str) -> str:
    if module_name == "qy.core":
        return "内建算子"
    return f"模块 {module_name}"
