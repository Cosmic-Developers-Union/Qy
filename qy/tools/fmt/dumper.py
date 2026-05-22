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
from qy.frontend.reader import DottedTuple
from qy.frontend.reader import Form
from qy.frontend.reader import Symbol

__all__ = ["dump_form", "dump_program"]

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
    if not form:
        return f"{prefix}()"

    lines: list[str] = [f"{prefix}("]
    lines.extend(f"{dump_form(item, indent + 1)}," for item in cast("Iterable[object]", form))
    lines.append(f"{prefix})")
    return "\n".join(lines)
