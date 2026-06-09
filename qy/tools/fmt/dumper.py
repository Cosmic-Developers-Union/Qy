# coding: utf-8
"""格式化工具函数。.

提供 AST dump 功能，用于调试和显示。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.frontend.cst import CstAtom
from qy.frontend.cst import CstList
from qy.frontend.cst import CstProgram
from qy.frontend.reader import DottedTuple
from qy.frontend.reader import Form
from qy.frontend.reader import Symbol

__all__ = ["dump_cst", "dump_form", "dump_program"]

INDENT = "  "


def dump_program(forms: Iterable[Form]) -> str:
    """将 forms 列表转换为可读的 dump 字符串。."""
    return "\n".join(dump_form(form) for form in forms)


def dump_form(form: object, indent: int = 0) -> str:
    """将单个 form 转换为可读的 dump 字符串。."""
    prefix = INDENT * indent
    if isinstance(form, Symbol):
        return f"{prefix}Symbol({form.name!r})"
    if isinstance(form, DottedTuple):
        lines: list[str] = [f"{prefix}DottedTuple("]
        lines.extend(f"{dump_form(item, indent + 1)}," for item in form)
        lines.append(f"{prefix}{INDENT}.")
        lines.append(f"{dump_form(cast(Form, form.tail), indent + 1)},")
        lines.append(f"{prefix})")
        return "\n".join(lines)
    if is_nil(form):
        return f"{prefix}EmptyChain()"
    if is_chain(form):
        lines: list[str] = [f"{prefix}Chain("]
        try:
            lines.extend(
                f"{dump_form(item, indent + 1)}," for item in cast("Iterable[object]", form)
            )
        except (TypeError, ValueError):
            # Improper list
            chain_form = cast(Chain, form)
            lines.append(f"{dump_form(chain_form.head, indent + 1)},")
            lines.append(f"{prefix}{INDENT}.")
            lines.append(f"{dump_form(chain_form.tail, indent + 1)},")
        lines.append(f"{prefix})")
        return "\n".join(lines)
    if isinstance(form, tuple | list):
        if not form:
            return f"{prefix}()"
        lines: list[str] = [f"{prefix}("]
        lines.extend(f"{dump_form(item, indent + 1)}," for item in form)
        lines.append(f"{prefix})")
        return "\n".join(lines)

    return f"{prefix}{form!r}"


def dump_cst(program: CstProgram) -> str:
    """Dump a CstProgram into a readable representation."""
    lines: list[str] = ["CstProgram("]
    for child in program.children:
        lines.append(_dump_cst_node(child, indent=1))
    if program.trailing_trivia:
        lines.append(f"{INDENT}trailing_trivia={program.trailing_trivia!r}")
    lines.append(")")
    return "\n".join(lines)


def _dump_cst_node(node: CstAtom | CstList, indent: int) -> str:
    prefix = INDENT * indent
    if isinstance(node, CstAtom):
        parts = [f"kind={node.kind.value}", f"text={node.text!r}"]
        if node.leading_trivia:
            parts.append(f"leading_trivia={node.leading_trivia!r}")
        return f"{prefix}CstAtom({', '.join(parts)})"
    lines: list[str] = [f"{prefix}CstList("]
    if node.leading_trivia:
        lines.append(f"{prefix}{INDENT}leading_trivia={node.leading_trivia!r}")
    for child in node.children:
        lines.append(_dump_cst_node(child, indent=indent + 1))
    if node.tail is not None:
        if node.dot_trivia:
            lines.append(f"{prefix}{INDENT}dot_trivia={node.dot_trivia!r}")
        lines.append(f"{prefix}{INDENT}.")
        lines.append(_dump_cst_node(node.tail, indent=indent + 1))
    if node.close_trivia:
        lines.append(f"{prefix}{INDENT}close_trivia={node.close_trivia!r}")
    lines.append(f"{prefix})")
    return "\n".join(lines)
