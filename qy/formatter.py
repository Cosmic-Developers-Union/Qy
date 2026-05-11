# coding: utf-8

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import Symbol
from qy.reader import read
from qy.reader import write

__all__ = ["dump_form", "dump_program", "format_form", "format_program", "format_source"]

MAX_INLINE_LENGTH = 80
INDENT = "  "


def format_source(source: str) -> str:
    return format_program(read(source))


def format_program(forms: Iterable[Form]) -> str:
    return "\n".join(format_form(form) for form in forms) + "\n"


def format_form(form: Form, indent: int = 0) -> str:
    if isinstance(form, Symbol):
        return write(form)
    if isinstance(form, DottedTuple):
        return _format_dotted(form, indent)
    if _is_quote_form(form):
        return "'" + format_form(form[1], indent)

    inline = _format_inline(form)
    if len(inline) <= MAX_INLINE_LENGTH and not _contains_complex_list(form):
        return inline

    if not form:
        return "()"

    current_indent = INDENT * indent
    child_indent = INDENT * (indent + 1)
    lines = [f"({format_form(form[0], indent)}"]
    lines.extend(f"{child_indent}{format_form(item, indent + 1)}" for item in form[1:])
    lines[-1] = f"{lines[-1]})"
    return "\n".join(
        f"{current_indent}{line}" if index == 0 else line for index, line in enumerate(lines)
    )


def dump_program(forms: Iterable[Form]) -> str:
    return "\n".join(dump_form(form) for form in forms)


def dump_form(form: Form, indent: int = 0) -> str:
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
    if not form:
        return f"{prefix}()"

    lines: list[str] = [f"{prefix}("]
    lines.extend(f"{dump_form(item, indent + 1)}," for item in form)
    lines.append(f"{prefix})")
    return "\n".join(lines)


def _format_inline(form: Form) -> str:
    if isinstance(form, Symbol):
        return write(form)
    if isinstance(form, DottedTuple):
        head = " ".join(_format_inline(item) for item in form)
        return f"({head} . {_format_inline(cast(Form, form.tail))})"
    if _is_quote_form(form):
        return "'" + _format_inline(form[1])
    return f"({' '.join(_format_inline(item) for item in form)})"


def _format_dotted(form: DottedTuple, indent: int) -> str:
    del indent
    return _format_inline(form)


def _contains_complex_list(form: Form) -> bool:
    if isinstance(form, Symbol):
        return False
    return any(isinstance(item, tuple) and not _is_quote_form(item) for item in form[1:])


def _is_quote_form(form: Form) -> bool:
    return isinstance(form, tuple) and len(form) == 2 and form[0] == Symbol("quote")
