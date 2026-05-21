# coding: utf-8
"""Form 格式化器。.

将 Qy AST form 转换为格式化的源码字符串。
支持 quote (`'`), quasiquote (`` ` ``), unquote (`,`), unquote-splicing (`,@`) 语法。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from qy.core.syntax import Chain
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import Symbol
from qy.reader import write

__all__ = ["format_form", "format_program"]

MAX_INLINE_LENGTH = 80
INDENT = "  "


def format_program(forms: Iterable[Form]) -> str:
    """将 forms 列表格式化为程序字符串。."""
    return "\n".join(format_form(form) for form in forms) + "\n"


def format_form(form: object, indent: int = 0) -> str:
    """将单个 form 格式化为字符串。.

    Args:
        form: 要格式化的 form
        indent: 当前缩进级别

    Returns:
        格式化后的字符串
    """
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

        first_line = f"({format_form(form[0], indent)}"
        body_start = 1
        for i, item in enumerate(form[1:], 1):
            if _is_complex(item):
                break
            rendered = _format_inline(item)
            candidate = f"{first_line} {rendered}"
            if len(candidate) > MAX_INLINE_LENGTH:
                break
            first_line = candidate
            body_start = i + 1

        lines = [first_line]
        for item in form[body_start:]:
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


def _format_chain(form: Chain | object, indent: int) -> str:
    """格式化 Chain 或 nil。."""
    if is_nil(form):
        return "()"

    if not is_chain(form):
        return "()"

    chain_form = cast(Chain, form)

    # Check if it's a quote form
    if _is_quote_form_chain(form):
        try:
            items = list(cast("Iterable[object]", form))
            return "'" + format_form(items[1], indent)
        except (TypeError, ValueError):
            pass

    # Check if it's a quasiquote form (`` ` ``)
    if _is_quasiquote_form_chain(form):
        try:
            items = list(cast("Iterable[object]", form))
            return "`" + format_form(items[1], indent)
        except (TypeError, ValueError):
            pass

    # Check if it's an unquote form (`,`)
    if _is_unquote_form_chain(form):
        try:
            items = list(cast("Iterable[object]", form))
            return "," + format_form(items[1], indent)
        except (TypeError, ValueError):
            pass

    # Check if it's an unquote-splicing form (`,@`)
    if _is_unquote_splicing_form_chain(form):
        try:
            items = list(cast("Iterable[object]", form))
            return ",@" + format_form(items[1], indent)
        except (TypeError, ValueError):
            pass

    # Check if it's an improper list (dotted pair)
    if not is_chain(chain_form.tail) and not is_nil(chain_form.tail):
        # Improper list: (a . b)
        return f"({format_form(chain_form.head, indent)} . {format_form(chain_form.tail, indent)})"

    # Try inline format first
    inline = _format_inline(form)

    # Convert to list for easier processing
    try:
        items = list(cast("Iterable[object]", form))
    except (TypeError, ValueError):
        # If iteration fails, it's an improper list
        return f"({format_form(chain_form.head, indent)} . {format_form(chain_form.tail, indent)})"

    if len(inline) <= MAX_INLINE_LENGTH and not _contains_complex_list(form):
        return inline

    if not items:
        return "()"

    current_indent = INDENT * indent
    child_indent = INDENT * (indent + 1)

    # Build first line: head + consecutive simple args that fit
    first_line = f"({format_form(items[0], indent)}"
    body_start = 1
    for i, item in enumerate(items[1:], 1):
        if _is_complex(item):
            break
        rendered = _format_inline(item)
        candidate = f"{first_line} {rendered}"
        if len(candidate) > MAX_INLINE_LENGTH:
            break
        first_line = candidate
        body_start = i + 1

    if body_start >= len(items):
        return inline

    lines = [first_line]
    for item in items[body_start:]:
        formatted = format_form(item, indent + 1)
        if "\n" in formatted:
            lines.append(formatted)
        else:
            lines.append(f"{child_indent}{formatted}")
    lines[-1] = f"{lines[-1]})"
    return "\n".join(
        f"{current_indent}{line}" if index == 0 else line for index, line in enumerate(lines)
    )


def _format_inline(form: object) -> str:
    """内联格式化 form。."""
    if isinstance(form, Symbol):
        return write(form)
    if isinstance(form, DottedTuple):
        head = " ".join(_format_inline(item) for item in form)
        return f"({head} . {_format_inline(cast(Form, form.tail))})"
    if is_chain(form) or is_nil(form):
        if is_nil(form):
            return "()"

        # Check for quote forms
        if _is_quote_form_chain(form):
            try:
                items = list(cast("Iterable[object]", form))
                return "'" + _format_inline(items[1])
            except (TypeError, ValueError):
                pass

        # Check for quasiquote
        if _is_quasiquote_form_chain(form):
            try:
                items = list(cast("Iterable[object]", form))
                return "`" + _format_inline(items[1])
            except (TypeError, ValueError):
                pass

        # Check for unquote
        if _is_unquote_form_chain(form):
            try:
                items = list(cast("Iterable[object]", form))
                return "," + _format_inline(items[1])
            except (TypeError, ValueError):
                pass

        # Check for unquote-splicing
        if _is_unquote_splicing_form_chain(form):
            try:
                items = list(cast("Iterable[object]", form))
                return ",@" + _format_inline(items[1])
            except (TypeError, ValueError):
                pass

        # Check for improper list
        chain_form = cast(Chain, form)
        if is_chain(form) and not is_chain(chain_form.tail) and not is_nil(chain_form.tail):
            return f"({_format_inline(chain_form.head)} . {_format_inline(chain_form.tail)})"
        try:
            return f"({' '.join(_format_inline(item) for item in cast('Iterable[object]', form))})"
        except (TypeError, ValueError):
            # Improper list fallback
            if is_chain(form):
                return f"({_format_inline(chain_form.head)} . {_format_inline(chain_form.tail)})"
            return "()"
    if isinstance(form, tuple) and _is_quote_form(form):
        return "'" + _format_inline(form[1])
    if isinstance(form, tuple):
        return f"({' '.join(_format_inline(item) for item in form)})"
    return str(form)


def _format_dotted(form: DottedTuple, indent: int) -> str:
    """格式化 DottedTuple。."""
    del indent
    return _format_inline(form)


def _is_complex(form: object) -> bool:
    """检查 form 是否复杂（需要多行）。."""
    if isinstance(form, Symbol):
        return False
    if is_nil(form):
        return False
    if isinstance(form, (tuple, Chain)) or is_chain(form):
        inline = _format_inline(form)
        return len(inline) > 12 or _contains_complex_list(form)
    return False


def _contains_complex_list(form: object) -> bool:
    """检查 form 是否包含复杂列表。."""
    if isinstance(form, Symbol):
        return False
    if is_nil(form):
        return False
    if is_chain(form):
        try:
            items = list(cast("Iterable[object]", form))
        except (TypeError, ValueError):
            # Improper list
            return False
        if len(items) <= 1:
            return False
        return any(
            isinstance(item, (tuple, Chain))
            and not _is_quote_form(item)
            and not _is_quote_form_chain(item)
            and not _is_quasiquote_form_chain(item)
            for item in items[1:]
        )
    # Fallback for tuple (legacy)
    if isinstance(form, tuple):
        return any(isinstance(item, tuple) and not _is_quote_form(item) for item in form[1:])
    return False


def _is_quote_form(form: object) -> bool:
    """检查是否是 quote form (tuple 形式)。."""
    return isinstance(form, tuple) and len(form) == 2 and form[0] == Symbol("quote")


def _is_quote_form_chain(form: object) -> bool:
    """检查是否是 quote form ('x -> (quote x))。."""
    if not is_chain(form):
        return False
    try:
        items = list(cast("Iterable[object]", form))
        return len(items) == 2 and items[0] == Symbol("quote")
    except (TypeError, ValueError):
        return False


def _is_quasiquote_form_chain(form: object) -> bool:
    """检查是否是 quasiquote form (`` `x `` -> (quasiquote x))。."""
    if not is_chain(form):
        return False
    try:
        items = list(cast("Iterable[object]", form))
        return len(items) == 2 and items[0] == Symbol("quasiquote")
    except (TypeError, ValueError):
        return False


def _is_unquote_form_chain(form: object) -> bool:
    """检查是否是 unquote form (`,x` -> (unquote x))。."""
    if not is_chain(form):
        return False
    try:
        items = list(cast("Iterable[object]", form))
        return len(items) == 2 and items[0] == Symbol("unquote")
    except (TypeError, ValueError):
        return False


def _is_unquote_splicing_form_chain(form: object) -> bool:
    """检查是否是 unquote-splicing form (`,@x` -> (unquote-splicing x))。."""
    if not is_chain(form):
        return False
    try:
        items = list(cast("Iterable[object]", form))
        return len(items) == 2 and items[0] == Symbol("unquote-splicing")
    except (TypeError, ValueError):
        return False
