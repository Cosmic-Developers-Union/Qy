# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/tools/fmt/*

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.reader import write

__all__ = ["dump_form", "dump_program", "format_form", "format_program", "format_source"]

MAX_INLINE_LENGTH = 80
INDENT = "  "


@dataclass(frozen=True, slots=True)
class _LineParts:
    code: str
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class _FormattedLine:
    code: str = ""
    comment: str | None = None
    raw: str | None = None


def format_source(source: str) -> str:
    forms = read(source)
    if not forms:
        return _format_trivia_only(source)
    return _format_source_with_trivia(source, forms)


def format_program(forms: Iterable[Form]) -> str:
    return "\n".join(format_form(form) for form in forms) + "\n"


def format_form(form: Form, indent: int = 0) -> str:
    if isinstance(form, Symbol):
        return write(form)
    if isinstance(form, DottedTuple):
        return _format_dotted(form, indent)
    if is_chain(form) or is_nil(form):
        return _format_chain(form, indent)
    if isinstance(form, tuple) and _is_quote_form(form):
        return "'" + format_form(form[1], indent)

    # Fallback for tuple (legacy)
    if isinstance(form, tuple):
        inline = _format_inline(form)
        if len(inline) <= MAX_INLINE_LENGTH and not _contains_complex_list(form):
            return inline

        if not form:
            return "()"

        current_indent = INDENT * indent
        child_indent = INDENT * (indent + 1)
        lines = [f"({format_form(form[0], indent)}"]
        for item in form[1:]:
            formatted = format_form(item, indent + 1)
            if "\n" in formatted:
                lines.append(formatted)
            else:
                lines.append(f"{child_indent}{formatted}")
        lines[-1] = f"{lines[-1]})"
        return "\n".join(
            f"{current_indent}{line}" if index == 0 else line for index, line in enumerate(lines)
        )

    return "()"


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
    if is_nil(form):
        return f"{prefix}QyNil()"
    if is_chain(form):
        lines: list[str] = [f"{prefix}Chain("]
        try:
            lines.extend(f"{dump_form(item, indent + 1)}," for item in form)
        except (TypeError, ValueError):
            # Improper list
            lines.append(f"{dump_form(form.head, indent + 1)},")
            lines.append(f"{prefix}{INDENT}.")
            lines.append(f"{dump_form(form.tail, indent + 1)},")
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
    if is_chain(form) or is_nil(form):
        if is_nil(form):
            return "()"
        if _is_quote_form_chain(form):
            try:
                items = list(form)
                return "'" + _format_inline(items[1])
            except (TypeError, ValueError):
                pass
        # Check for improper list
        if is_chain(form) and not is_chain(form.tail) and not is_nil(form.tail):
            return f"({_format_inline(form.head)} . {_format_inline(form.tail)})"
        try:
            return f"({' '.join(_format_inline(item) for item in form)})"
        except (TypeError, ValueError):
            # Improper list fallback
            if is_chain(form):
                return f"({_format_inline(form.head)} . {_format_inline(form.tail)})"
            return "()"
    if isinstance(form, tuple) and _is_quote_form(form):
        return "'" + _format_inline(form[1])
    if isinstance(form, tuple):
        return f"({' '.join(_format_inline(item) for item in form)})"
    return str(form)


def _format_dotted(form: DottedTuple, indent: int) -> str:
    del indent
    return _format_inline(form)


def _contains_complex_list(form: Form) -> bool:
    if isinstance(form, Symbol):
        return False
    if is_nil(form):
        return False
    if is_chain(form):
        try:
            items = list(form)
        except (TypeError, ValueError):
            # Improper list
            return False
        if len(items) <= 1:
            return False
        return any(isinstance(item, (tuple, Chain)) and not _is_quote_form(item) and not _is_quote_form_chain(item) for item in items[1:])
    # Fallback for tuple (legacy)
    if isinstance(form, tuple):
        return any(isinstance(item, tuple) and not _is_quote_form(item) for item in form[1:])
    return False


def _is_quote_form(form: Form) -> bool:
    return isinstance(form, tuple) and len(form) == 2 and form[0] == Symbol("quote")


def _is_quote_form_chain(form: Form) -> bool:
    if not is_chain(form):
        return False
    try:
        items = list(form)
        return len(items) == 2 and items[0] == Symbol("quote")
    except (TypeError, ValueError):
        return False


def _format_chain(form: Chain | object, indent: int) -> str:
    if is_nil(form):
        return "()"

    if not is_chain(form):
        return "()"

    # Check if it's a quote form
    if _is_quote_form_chain(form):
        try:
            items = list(form)
            return "'" + format_form(items[1], indent)
        except (TypeError, ValueError):
            pass

    # Check if it's an improper list (dotted pair)
    if not is_chain(form.tail) and not is_nil(form.tail):
        # Improper list: (a . b)
        return f"({format_form(form.head, indent)} . {format_form(form.tail, indent)})"

    # Try inline format first
    inline = _format_inline(form)

    # Convert to list for easier processing
    try:
        items = list(form)
    except (TypeError, ValueError):
        # If iteration fails, it's an improper list
        return f"({format_form(form.head, indent)} . {format_form(form.tail, indent)})"

    if len(inline) <= MAX_INLINE_LENGTH and not _contains_complex_list(form):
        return inline

    if not items:
        return "()"

    current_indent = INDENT * indent
    child_indent = INDENT * (indent + 1)
    lines = [f"({format_form(items[0], indent)}"]
    for item in items[1:]:
        formatted = format_form(item, indent + 1)
        if "\n" in formatted:
            lines.append(formatted)
        else:
            lines.append(f"{child_indent}{formatted}")
    lines[-1] = f"{lines[-1]})"
    return "\n".join(
        f"{current_indent}{line}" if index == 0 else line for index, line in enumerate(lines)
    )


def _format_source_with_trivia(source: str, forms: list[Form]) -> str:
    line_parts = _split_source_lines(source)
    lines: list[_FormattedLine] = []
    previous_end_line = 0

    for form in forms:
        span = get_span(form)
        if span is None or span.line is None or span.end_line is None:
            lines.extend(_format_form_lines(form, None))
            continue

        start_line = span.line
        end_line = span.end_line
        lines.extend(_preserved_lines(line_parts, previous_end_line + 1, start_line - 1))
        lines.extend(_interior_comment_lines(line_parts, start_line, end_line))

        trailing_comment = line_parts[end_line - 1].comment if end_line <= len(line_parts) else None
        lines.extend(_format_form_lines(form, trailing_comment))
        previous_end_line = end_line

    lines.extend(_preserved_lines(line_parts, previous_end_line + 1, len(line_parts)))
    return _render_lines(lines)


def _format_form_lines(form: Form, trailing_comment: str | None) -> list[_FormattedLine]:
    formatted = format_form(form).splitlines() or [""]
    lines = [_FormattedLine(code=line) for line in formatted]
    if trailing_comment:
        lines[-1] = _FormattedLine(code=lines[-1].code, comment=trailing_comment.strip())
    return lines


def _preserved_lines(
    line_parts: list[_LineParts],
    start_line: int,
    end_line: int,
) -> list[_FormattedLine]:
    if start_line > end_line:
        return []

    lines: list[_FormattedLine] = []
    for line_no in range(start_line, end_line + 1):
        if line_no < 1 or line_no > len(line_parts):
            continue
        part = line_parts[line_no - 1]
        raw = _preserve_blank_or_comment(part)
        if raw is not None:
            lines.append(_FormattedLine(raw=raw))
    return lines


def _interior_comment_lines(
    line_parts: list[_LineParts],
    start_line: int,
    end_line: int,
) -> list[_FormattedLine]:
    lines: list[_FormattedLine] = []
    for line_no in range(start_line, max(start_line, end_line)):
        if line_no < 1 or line_no > len(line_parts):
            continue
        part = line_parts[line_no - 1]
        if part.comment is not None:
            lines.append(_FormattedLine(raw=_comment_only(part)))
    return lines


def _preserve_blank_or_comment(part: _LineParts) -> str | None:
    if part.comment is not None and not part.code.strip():
        return _comment_only(part)
    if not part.code.strip() and part.comment is None:
        return ""
    return None


def _comment_only(part: _LineParts) -> str:
    indent = part.code[: len(part.code) - len(part.code.lstrip())]
    return f"{indent}{part.comment.strip()}" if part.comment else indent.rstrip()


def _render_lines(lines: list[_FormattedLine]) -> str:
    rendered: list[str] = []
    group: list[_FormattedLine] = []

    def flush_group() -> None:
        if not group:
            return
        target_column = max((len(line.code) for line in group if line.comment), default=0) + 2
        for line in group:
            if line.comment:
                padding = " " * max(target_column - len(line.code), 1)
                rendered.append(f"{line.code.rstrip()}{padding}{line.comment}")
            else:
                rendered.append(line.code.rstrip())
        group.clear()

    for line in lines:
        if line.raw is not None:
            flush_group()
            rendered.append(line.raw.rstrip())
        else:
            group.append(line)
    flush_group()
    return "\n".join(rendered).rstrip("\n") + "\n"


def _format_trivia_only(source: str) -> str:
    line_parts = _split_source_lines(source)
    rendered: list[str] = []
    for part in line_parts:
        line = _preserve_blank_or_comment(part)
        if line is not None:
            rendered.append(line)
    if not rendered:
        return "\n" if source.endswith("\n") else ""
    return "\n".join(line.rstrip() for line in rendered) + "\n"


def _split_source_lines(source: str) -> list[_LineParts]:
    lines = source.splitlines()
    parts: list[_LineParts] = []
    in_multiline = False
    for line in lines:
        comment_index, in_multiline = _comment_start(line, in_multiline)
        if comment_index is None:
            parts.append(_LineParts(code=line.rstrip(), comment=None))
        else:
            parts.append(
                _LineParts(
                    code=line[:comment_index].rstrip(),
                    comment=line[comment_index:].rstrip(),
                )
            )
    return parts


def _comment_start(line: str, in_multiline: bool) -> tuple[int | None, bool]:
    index = 0
    while index < len(line):
        if in_multiline:
            end = line.find('"""', index)
            if end == -1:
                return None, True
            index = end + 3
            in_multiline = False
            continue

        if line.startswith('"""', index):
            in_multiline = True
            index += 3
            continue
        char = line[index]
        if char == ";":
            return index, in_multiline
        if char == '"':
            index = _skip_quoted_symbol(line, index + 1)
            continue
        index += 1
    return None, in_multiline


def _skip_quoted_symbol(line: str, index: int) -> int:
    escaped = False
    while index < len(line):
        char = line[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return index + 1
        index += 1
    return index
