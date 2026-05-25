# coding: utf-8
"""源码格式化（CST-based）。.

使用 CST 保留 trivia（注释、空行）信息，再用 format_form 重格式化代码节点。
"""

from __future__ import annotations

from dataclasses import dataclass

from qy.frontend.cst import CstNode
from qy.frontend.cst import CstProgram
from qy.frontend.reader import parse_cst
from qy.frontend.reader import read_cst
from qy.frontend.surface import expand_surface_dialect
from qy.tools.fmt.formatter import format_form

__all__ = ["format_source"]


@dataclass(frozen=True, slots=True)
class _FormattedLine:
    """A line in the formatted output.

    `code` is the form code; `comment` (if any) is appended to that line.
    `raw` represents a stand-alone comment or blank line.
    """

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
    from qy.frontend.cst_parser import CstParseError
    from qy.frontend.reader import ReaderSyntaxError

    try:
        cst = parse_cst(source)
    except CstParseError as e:
        raise ReaderSyntaxError(str(e), span=e.span) from e
    if not cst.children:
        return _format_trailing_only(cst.trailing_trivia)
    return _render_lines(_collect_lines(cst))


def _collect_lines(cst: CstProgram) -> list[_FormattedLine]:
    lines: list[_FormattedLine] = []
    children = cst.children
    for index, node in enumerate(children):
        # Convert leading trivia → list of raw lines (blank/comment-only)
        # but skip the same-line trailing comment which belongs to the previous form.
        leading = node.leading_trivia
        post_trailing, blank_and_comment = _split_leading_trivia(leading, has_previous=index > 0)

        # Apply trailing comment to the previous form (if any)
        if post_trailing is not None and lines:
            last = lines[-1]
            if last.raw is None and last.comment is None:
                lines[-1] = _FormattedLine(code=last.code, comment=post_trailing)

        # Emit blank lines and standalone comment lines
        lines.extend(_FormattedLine(raw=line) for line in blank_and_comment)

        # Emit the form
        form = _node_to_form(node)
        formatted = format_form(form).splitlines() or [""]
        for code_line in formatted:
            lines.append(_FormattedLine(code=code_line))

    # Handle trailing trivia at end of file
    _, tail_lines = _split_leading_trivia(cst.trailing_trivia, has_previous=True)
    # The first line of trailing trivia might contain a trailing comment for the last form
    trailing_comment_for_last = _extract_trailing_comment(cst.trailing_trivia)
    if trailing_comment_for_last is not None and lines:
        last = lines[-1]
        if last.raw is None and last.comment is None:
            lines[-1] = _FormattedLine(code=last.code, comment=trailing_comment_for_last)
    lines.extend(_FormattedLine(raw=line) for line in tail_lines)
    return lines


def _node_to_form(node: CstNode) -> object:
    """Convert a single CstNode to a Form (with surface dialect expansion)."""
    forms = read_cst(CstProgram(children=(node,), trailing_trivia="", span=node.span))
    expanded = expand_surface_dialect(forms)
    return expanded[0]


def _split_leading_trivia(trivia: str, *, has_previous: bool) -> tuple[str | None, list[str]]:
    """Process trivia preceding a form.

    Returns (trailing_comment_for_prev, [standalone_lines]).

    If there's a previous form on the same line as the start of trivia,
    a leading comment on that same line becomes the previous form's
    trailing comment. Otherwise it's a standalone line.

    All subsequent lines (blank or comment) become standalone entries.
    """
    if not trivia:
        return None, []

    parts = trivia.split("\n")
    trailing: str | None = None
    standalone: list[str] = []

    first = parts[0]
    first_stripped = first.strip()
    if has_previous and first_stripped.startswith(";"):
        trailing = first_stripped
    elif first_stripped:
        # No previous form on same line: treat as standalone
        if first_stripped.startswith(";"):
            standalone.append(first_stripped)

    # Lines in the middle (parts[1..len-2])
    for line in parts[1:-1]:
        stripped = line.strip()
        if not stripped:
            standalone.append("")
        elif stripped.startswith(";"):
            standalone.append(stripped)

    return trailing, standalone


def _extract_trailing_comment(trivia: str) -> str | None:
    """Extract a same-line trailing comment from the start of trivia."""
    if not trivia:
        return None
    first_line, _, _ = trivia.partition("\n")
    stripped = first_line.strip()
    if stripped.startswith(";"):
        return stripped
    return None


def _format_trailing_only(trivia: str) -> str:
    """Format a source consisting only of trivia."""
    if not trivia:
        return ""
    parts = trivia.split("\n")
    # Drop the final empty fragment if the source ended with newline
    if parts and parts[-1] == "":
        parts = parts[:-1]
    rendered: list[str] = []
    for line in parts:
        stripped = line.strip()
        if not stripped:
            rendered.append("")
        elif stripped.startswith(";"):
            rendered.append(stripped)
    if not rendered:
        return "\n" if trivia.endswith("\n") else ""
    return "\n".join(rendered) + "\n"


def _render_lines(lines: list[_FormattedLine]) -> str:
    """Render lines to a final string with comment alignment."""
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
