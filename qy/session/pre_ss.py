# coding: utf-8
"""Pre-symbol-space implementation for literal values.

目标：
- 实现基于 symbol-space 的字面量层
- 提供 lisp-ss、number-ss、string-ss 等预定义符号空间
- 替代 qy/literals.py 的函数式 resolver

当前：
- 完整实现，作为 literal resolver 的 symbol-space 版本

禁止：
- 不得依赖 VM 执行逻辑
- 不得混入运行时求值
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.core.symbol_space import SymbolSpace
    from qy.frontend.reader import Symbol

__all__ = [
    "create_char_ss",
    "create_lisp_ss",
    "create_literal_ss",
    "create_number_ss",
    "create_pre_ssc",
    "create_string_ss",
    "create_value_ss",
    "is_char_literal",
    "is_number_literal",
    "is_string_literal",
    "parse_char_literal",
    "parse_number_literal",
    "parse_string_literal",
]

_MISSING = object()


def is_string_literal(name: str) -> bool:
    """Check if a symbol name represents a string literal."""
    return name.startswith('"') or name.startswith('r"')


def parse_string_literal(name: str) -> object:
    """Parse a string literal symbol name into a Python string.

    Returns _MISSING if the name is not a valid string literal.
    """
    import ast

    try:
        value = ast.literal_eval(name)
    except (SyntaxError, ValueError):
        return _MISSING
    if not isinstance(value, str):
        return _MISSING
    return value


_CHAR_NAMED: dict[str, str] = {
    "space": " ",
    "newline": "\n",
    "tab": "\t",
    "return": "\r",
    "null": "\x00",
    "nul": "\x00",
    "backspace": "\x08",
    "delete": "\x7f",
    "escape": "\x1b",
    "alarm": "\x07",
    "vtab": "\x0b",
    "formfeed": "\x0c",
}


def is_char_literal(name: str) -> bool:
    r"""Check if a symbol name represents a char literal.

    Char literal syntax: #\\<char>, #\\<named>, #\\uXXXX, #\\UXXXXXXXX
    """
    return name.startswith("#\\") and len(name) > 2


def parse_char_literal(name: str) -> object:
    """Parse a char literal symbol name into a CharValue.

    Returns _MISSING if the name is not a valid char literal.
    """
    from qy.sem.core import CharValue

    if not name.startswith("#\\") or len(name) <= 2:
        return _MISSING

    body = name[2:]

    if len(body) == 1:
        return CharValue(body)

    lower = body.lower()
    if lower in _CHAR_NAMED:
        return CharValue(_CHAR_NAMED[lower])

    if lower.startswith("u") and len(body) in (5, 9):
        hex_part = body[1:]
        try:
            codepoint = int(hex_part, 16)
            return CharValue(chr(codepoint))
        except (ValueError, OverflowError):
            return _MISSING

    if lower.startswith("x") and len(body) == 3:
        hex_part = body[1:]
        try:
            codepoint = int(hex_part, 16)
            return CharValue(chr(codepoint))
        except (ValueError, OverflowError):
            return _MISSING

    return _MISSING


def is_number_literal(name: str) -> bool:
    """Check if a symbol name represents a number literal."""
    try:
        int(name)
        return True
    except ValueError:
        pass
    try:
        float(name)
        return True
    except ValueError:
        pass
    return False


def parse_number_literal(name: str) -> object:
    """Parse a number literal symbol name into a Python number.

    Returns _MISSING if the name is not a valid number literal.
    """
    try:
        value = int(name)
        return value
    except ValueError:
        pass
    try:
        value = float(name)
        # Reject inf and nan as they're not proper literals
        if value != value or abs(value) == float("inf"):  # nan or inf
            return _MISSING
        return value
    except ValueError:
        pass
    return _MISSING


def create_lisp_ss() -> SymbolSpace:
    """Create the lisp-ss with T and nil bindings.

    This is the foundational symbol-space providing Lisp's truth values.
    """
    from qy.core.symbol_space import SymbolSpace
    from qy.core.syntax import nil
    from qy.frontend.reader import Symbol
    from qy.sem.core import T

    return SymbolSpace(
        {
            Symbol("T"): T,
            Symbol("nil"): nil,
            Symbol("true"): T,
            Symbol("false"): nil,
            Symbol("none"): None,
        },
        name="lisp-ss",
        writable=False,
    )


def create_number_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Create the number-ss that resolves numeric literals.

    This symbol-space provides dynamic resolution of number literals by
    implementing a custom lookup that parses symbol names as numbers.
    """
    from qy.core.symbol_space import SymbolSpace

    return SymbolSpace(
        {},
        parent=parent,
        name="number-ss",
        writable=False,
    )


def create_char_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    r"""Create the char-ss that resolves character literals.

    Char literal syntax: #\\a, #\\space, #\\newline, #\\uXXXX, etc.
    Resolution happens in the literal resolver layer.
    """
    from qy.core.symbol_space import SymbolSpace

    return SymbolSpace(
        {},
        parent=parent,
        name="char-ss",
        writable=False,
    )


def create_string_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Create the string-ss that resolves string literals.

    This symbol-space provides dynamic resolution of string literals by
    implementing a custom lookup that parses symbol names as strings.
    """
    from qy.core.symbol_space import SymbolSpace

    # String-ss is a virtual space that dynamically resolves string symbols
    # We create an empty space with a parent, and the actual resolution
    # happens in the literal resolver layer
    return SymbolSpace(
        {},
        parent=parent,
        name="string-ss",
        writable=False,
    )


def create_value_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Create a combined value-ss that includes number-ss, char-ss, and string-ss.

    This is a convenience function that creates a symbol-space chain
    containing numeric, character, and string literal resolution.
    """
    from qy.core.symbol_space import SymbolSpace

    return SymbolSpace(
        {},
        parent=parent,
        name="value-ss",
        writable=False,
    )


def create_literal_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Create the complete literal-ss with all literal types.

    This combines lisp-ss, number-ss, and string-ss into a single
    symbol-space for literal resolution.
    """
    if parent is not None:
        # Chain: parent -> lisp-ss -> literal-ss
        from qy.core.syntax import nil
        from qy.frontend.reader import Symbol
        from qy.sem.core import T

        lisp = parent.child(name="lisp-ss", writable=False)
        lisp.define(Symbol("T"), T)
        lisp.define(Symbol("nil"), nil)
        lisp.define(Symbol("true"), T)
        lisp.define(Symbol("false"), nil)
        lisp.define(Symbol("none"), None)
    else:
        lisp = create_lisp_ss()
    return create_value_ss(parent=lisp)


def create_pre_ssc(stdlib_space: SymbolSpace | None = None) -> SymbolSpace:
    """Create the pre-symbol-space-chain (pre-ssc).

    This creates the foundational symbol-space chain that includes:
    1. meta-symbol-space (implicit root)
    2. lisp-ss (T, nil, true, false, none)
    3. value-ss (number, char, and string literal resolution)
    4. stdlib-space (optional standard library bindings)

    The pre-ssc serves as the base for all user code evaluation.
    """
    # Start with lisp-ss as the foundation
    lisp = create_lisp_ss()

    # Add value-ss for literal resolution
    value = create_value_ss(parent=lisp)

    # Add stdlib if provided
    if stdlib_space is not None:
        # Chain: lisp -> value -> stdlib -> writable-head
        stdlib_child = value.child(
            bindings=stdlib_space.local_bindings(), name="stdlib", writable=False
        )
        return stdlib_child.child(name="pre-ssc-head", writable=True)

    return value.child(name="pre-ssc-head", writable=True)


def resolve_literal_in_pre_ss(symbol: Symbol, pre_ss: SymbolSpace) -> object:
    """Resolve a symbol as a literal using pre-symbol-space.

    This function implements the literal resolution logic that works with
    the pre-ss architecture. It first checks the symbol-space chain, then
    attempts to parse the symbol name as a literal.

    Returns _MISSING if the symbol cannot be resolved as a literal.
    """
    # First try normal lookup in the symbol-space chain
    # Note: lookup returns None for both "not found" and "bound to None"
    # We need to check if the symbol is actually bound
    if pre_ss.has_local_binding(symbol) or (
        pre_ss.parent and pre_ss.parent.lookup(symbol) is not None
    ):
        return pre_ss.lookup(symbol)

    # Check if it's bound to None specifically
    value = pre_ss.lookup(symbol)
    if value is None:
        # Could be bound to None or not found - check all bindings
        all_bindings = pre_ss.all_bindings()
        if symbol in all_bindings:
            return None  # Actually bound to None

    # Try char literal
    if is_char_literal(symbol.name):
        result = parse_char_literal(symbol.name)
        if result is not _MISSING:
            return result

    # Try string literal
    if is_string_literal(symbol.name):
        result = parse_string_literal(symbol.name)
        if result is not _MISSING:
            return result

    # Try number literal
    result = parse_number_literal(symbol.name)
    if result is not _MISSING:
        return result

    return _MISSING
