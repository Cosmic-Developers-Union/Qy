# coding: utf-8
"""源码格式化。.

处理带 trivia（注释、空行）的源码格式化。
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.reader import Form
from qy.reader import get_span
from qy.reader import read
from qy.tools.fmt.formatter import format_form

__all__ = ["format_source"]

MAX_INLINE_LENGTH = 80


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
    """格式化源码，保持注释和空行。.

    Args:
        source: 源码字符串

    Returns:
        格式化后的源码字符串
    """
    forms = read(source)
    if not forms:
        return _format_trivia_only(source)
    return _format_source_with_trivia(source, forms)


def _format_source_with_trivia(source: str, forms: list[Form]) -> str:
    """格式化带 trivia 的源码。."""
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
    """格式化单个 form 为行列表。."""
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
    """保留空行和注释行。."""
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
    """提取 form 内部的注释行。."""
    lines: list[_FormattedLine] = []
    for line_no in range(start_line, max(start_line, end_line)):
        if line_no < 1 or line_no > len(line_parts):
            continue
        part = line_parts[line_no - 1]
        if part.comment is not None:
            lines.append(_FormattedLine(raw=_comment_only(part)))
    return lines


def _preserve_blank_or_comment(part: _LineParts) -> str | None:
    """保留空行或仅注释的行。."""
    if part.comment is not None and not part.code.strip():
        return _comment_only(part)
    if not part.code.strip() and part.comment is None:
        return ""
    return None


def _comment_only(part: _LineParts) -> str:
    """提取仅注释的行。."""
    indent = part.code[: len(part.code) - len(part.code.lstrip())]
    return f"{indent}{part.comment.strip()}" if part.comment else indent.rstrip()


def _render_lines(lines: list[_FormattedLine]) -> str:
    """渲染行列表为最终字符串。."""
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
    """格式化仅包含 trivia（注释、空行）的源码。."""
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
    """将源码拆分为行，并分离注释。."""
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
    """查找注释的起始位置。."""
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
    """跳过引号字符串。."""
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
