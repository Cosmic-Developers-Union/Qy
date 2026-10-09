# coding: utf-8
"""源码格式化（CST-based）。.

使用 CST 保留 trivia（注释、空行）信息，再用 format_form 重格式化代码节点。
若某个顶层 form 的**内部**含注释，则用其 CST 原文渲染该 form（只做行尾空白清理），
保证 formatter 绝不丢注释；无内部注释的 form 正常规范化。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from qy.frontend.cst import CstAtom
from qy.frontend.cst import CstList
from qy.frontend.cst import CstNode
from qy.frontend.cst import CstProgram
from qy.frontend.cst import collect_text
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


# 只有 sequence 级 surface 前缀（quote / quasiquote）会与下一个 form 合成一个
# 逻辑 form；`,` / `,@` 只在 quasiquote 操作数内部出现（那时是 CstList 的子节点）。
_READER_PREFIXES = frozenset({"'", "`"})


def _is_reader_prefix(node: CstNode) -> bool:
    """读取器宏前缀（' ` , ,@）在 CST 里是独立的 CstAtom，和操作数是同一个逻辑 form。."""
    return isinstance(node, CstAtom) and node.text.strip() in _READER_PREFIXES


def _group_contains_comment(group: tuple[CstNode, ...]) -> bool:
    return any(_node_contains_comment(node) for node in group)


def _group_body_text(group: tuple[CstNode, ...]) -> str:
    """组原文（只去掉首个节点的 leading trivia）。."""
    parts: list[str] = []
    for index, node in enumerate(group):
        body = replace(node, leading_trivia="") if index == 0 else node
        parts.append(collect_text(CstProgram(children=(body,), trailing_trivia="", span=node.span)))
    return "".join(parts)


def _collect_lines(cst: CstProgram) -> list[_FormattedLine]:
    lines: list[_FormattedLine] = []
    children = cst.children
    index = 0
    group_index = 0
    while index < len(children):
        # 读取器宏前缀与其操作数在 CST 里是相邻子节点，但属于同一个 form；
        # 必须在格式化前重新分组，否则会输出成两个顶层 form（语义被改变）。
        group: list[CstNode] = [children[index]]
        # 仅当操作数紧邻前缀（无空白/注释）时才是同一个 reader-macro form；
        # `' x` 是符号 `'` 与 `x` 两个 form，不能合并。
        while (
            _is_reader_prefix(group[-1])
            and index + len(group) < len(children)
            and children[index + len(group)].leading_trivia == ""
        ):
            group.append(children[index + len(group)])

        # Convert leading trivia → list of raw lines (blank/comment-only)
        # but skip the same-line trailing comment which belongs to the previous form.
        leading = group[0].leading_trivia
        post_trailing, blank_and_comment = _split_leading_trivia(
            leading, has_previous=group_index > 0
        )

        # Apply trailing comment to the previous form (if any)
        if post_trailing is not None and lines:
            last_line = lines[-1]
            if last_line.raw is None and last_line.comment is None:
                lines[-1] = _FormattedLine(code=last_line.code, comment=post_trailing)

        # Emit blank lines and standalone comment lines
        lines.extend(_FormattedLine(raw=line) for line in blank_and_comment)

        # Emit the form. form 内部若含注释，用 CST 原文渲染，保证 formatter
        # 绝不丢注释；否则走规范化 formatter。
        if _group_contains_comment(tuple(group)):
            body_lines = _group_body_text(tuple(group)).splitlines() or [""]
            for code_line in body_lines:
                lines.append(_FormattedLine(code=code_line))
        else:
            form = _group_to_form(tuple(group))
            formatted = format_form(form).splitlines() or [""]
            for code_line in formatted:
                lines.append(_FormattedLine(code=code_line))

        index += len(group)
        group_index += 1

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


def _group_to_form(group: tuple[CstNode, ...]) -> object:
    """Convert a group of CST nodes to a single Form (with surface dialect expansion)."""
    forms = read_cst(CstProgram(children=group, trailing_trivia="", span=group[0].span))
    expanded = expand_surface_dialect(forms)
    return expanded[0]


def _has_comment(trivia: str) -> bool:
    return ";" in trivia


def _node_contains_comment(node: CstNode) -> bool:
    """节点**内部**是否含注释（不含自身 leading trivia，那由调用方处理）。."""
    if isinstance(node, CstList):
        if _has_comment(node.dot_trivia) or _has_comment(node.close_trivia):
            return True
        for child in node.children:
            if _has_comment(child.leading_trivia) or _node_contains_comment(child):
                return True
        if node.tail is not None:
            if _has_comment(node.tail.leading_trivia) or _node_contains_comment(node.tail):
                return True
    return False


def _node_body_text(node: CstNode) -> str:
    """节点原文（不含自身 leading trivia，其余 trivia 原样保留）。."""
    body = replace(node, leading_trivia="")
    return collect_text(CstProgram(children=(body,), trailing_trivia="", span=node.span))


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
