# coding: utf-8
"""Pre-symbol-space implementation for literal values.

目标：
- 实现基于 symbol-space 的字面量层
- 提供 lisp-ss、number-ss、string-ss 等预定义符号空间
- 提供 literal resolver 函数 (try_default_literal, resolve_default_literal, default_literal_type)

当前：
- 完整实现，作为 literal resolver 的 symbol-space 版本

禁止：
- 不得依赖 VM 执行逻辑
- 不得混入运行时求值
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.core.operator_signature import TypeName
    from qy.core.symbol_space import SymbolSpace
    from qy.frontend.reader import Symbol

from qy.core.symbol_space import MISSING as _MISSING

__all__ = [
    "create_char_ss",
    "create_lisp_ss",
    "create_literal_ss",
    "create_number_ss",
    "create_pre_ssc",
    "create_string_ss",
    "create_value_ss",
    "default_literal_type",
    "is_char_literal",
    "is_number_literal",
    "is_string_literal",
    "parse_char_literal",
    "parse_number_literal",
    "parse_string_literal",
    "resolve_default_literal",
    "try_default_literal",
]


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
    """Parse a number literal symbol name into a semantic number value.

    Returns IntValue for integer literals, FloatValue for float literals.
    Returns _MISSING if the name is not a valid number literal.
    """
    from qy.sem.core import FloatValue
    from qy.sem.core import IntValue

    try:
        value = int(name)
        return IntValue(value)
    except ValueError:
        pass
    try:
        value = float(name)
        # Reject inf and nan as they're not proper literals
        if value != value or abs(value) == float("inf"):  # nan or inf
            return _MISSING
        return FloatValue(value)
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
    from qy.sem.core import NONE
    from qy.sem.core import T

    return SymbolSpace(
        {
            Symbol("T"): T,
            Symbol("nil"): nil,
            Symbol("true"): T,
            Symbol("false"): nil,
            Symbol("none"): NONE,
        },
        name="lisp-ss",
        writable=False,
    )


def create_number_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Create the number-ss with both finite operators and infinite literals.

    number-ss 同时持有两类绑定:

    - **有限部分** (fixed bindings): ``+ - * / = == < > <= >= mod`` 等数字算子,
      由 ``qy.session.number_ops.number_ss_bindings()`` 提供。
    - **无限部分** (membership/resolver): 任何符合数字字面量 spelling 的 symbol
      (``42``, ``-3``, ``2.5``, ...) 通过 ``parse_number_literal`` 解析为
      ``IntValue`` / ``FloatValue``。

    这与语言模型一致: number-ss 是无限符号空间, 既绑定所有数字, 又包含 add 等
    算子。``(+ 1 2)`` 在 ssc 上找到 ``+`` 与 ``1`` ``2`` 时, 走的是同一条
    lookup 路径, 命中同一个空间。
    """
    from qy.core.symbol_space import SymbolSpace
    from qy.session.number_ops import number_ss_bindings

    return SymbolSpace(
        number_ss_bindings(),
        parent=parent,
        name="number-ss",
        writable=False,
        membership=lambda s: is_number_literal(s.name),
        resolver=_number_resolver,
    )


def _number_resolver(symbol: Symbol) -> object:
    return parse_number_literal(symbol.name)


def create_char_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    r"""Create the char-ss that resolves character literals.

    Char literal syntax: #\\a, #\\space, #\\newline, #\\uXXXX, etc.
    Resolution happens via the ``(membership, resolver)`` pair on the space.
    """
    from qy.core.symbol_space import SymbolSpace

    return SymbolSpace(
        {},
        parent=parent,
        name="char-ss",
        writable=False,
        membership=lambda s: is_char_literal(s.name),
        resolver=_char_resolver,
    )


def _char_resolver(symbol: Symbol) -> object:
    if not is_char_literal(symbol.name):
        return _MISSING
    return parse_char_literal(symbol.name)


def create_string_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Create the string-ss that resolves string literals.

    String literals are symbols whose spelling starts with ``"`` or ``r"``.
    Resolution happens via the ``(membership, resolver)`` pair on the space.
    """
    from qy.core.symbol_space import SymbolSpace

    return SymbolSpace(
        {},
        parent=parent,
        name="string-ss",
        writable=False,
        membership=lambda s: is_string_literal(s.name),
        resolver=_string_resolver,
    )


def _string_resolver(symbol: Symbol) -> object:
    if not is_string_literal(symbol.name):
        return _MISSING
    return parse_string_literal(symbol.name)


def create_value_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Build the value-ss layers: number-ss → char-ss → string-ss.

    Returns the head of a 3-node ssc segment that resolves any literal symbol
    spelling. The order is arbitrary because the three hooks are disjoint.
    """
    number = create_number_ss(parent=parent)
    char = create_char_ss(parent=number)
    string = create_string_ss(parent=char)
    return string


def create_literal_ss(parent: SymbolSpace | None = None) -> SymbolSpace:
    """Create the complete literal-ss with all literal types.

    Chain: parent (optional) → lisp-ss → number-ss → char-ss → string-ss.
    """
    from qy.core.syntax import nil
    from qy.frontend.reader import Symbol
    from qy.sem.core import NONE
    from qy.sem.core import T

    if parent is None:
        lisp = create_lisp_ss()
    else:
        lisp = parent.child(name="lisp-ss", writable=False)
        lisp.define(Symbol("T"), T)
        lisp.define(Symbol("nil"), nil)
        lisp.define(Symbol("true"), T)
        lisp.define(Symbol("false"), nil)
        lisp.define(Symbol("none"), NONE)
    return create_value_ss(parent=lisp)


def create_pre_ssc(stdlib_space: SymbolSpace | None = None) -> SymbolSpace:
    """Build the pre-symbol-space-chain (pre-ssc).

    Layered, parent-first:
      lisp-ss → number-ss → char-ss → string-ss → [stdlib] → pre-ssc-head

    Each layer has a single responsibility. Literal resolution is a real
    chain walk, not a fallback after the chain is exhausted.
    """
    lisp = create_lisp_ss()
    literals = create_value_ss(parent=lisp)

    if stdlib_space is not None:
        stdlib_child = literals.child(
            bindings=stdlib_space.local_bindings(), name="stdlib", writable=False
        )
        return stdlib_child.child(name="pre-ssc-head", writable=True)

    return literals.child(name="pre-ssc-head", writable=True)


def try_default_literal(symbol: Symbol) -> object:
    """Try to resolve a symbol as a literal value.

    Returns _MISSING if the symbol cannot be resolved.
    """
    from qy.core.syntax import nil
    from qy.sem.core import NONE
    from qy.sem.core import T

    name = symbol.name
    if name == "T" or name == "true":
        return T
    if name == "nil" or name == "false":
        return nil
    if name == "none":
        return NONE

    if is_char_literal(name):
        result = parse_char_literal(name)
        if result is not _MISSING:
            return result

    if is_string_literal(name):
        result = parse_string_literal(name)
        if result is not _MISSING:
            return result

    try:
        return int(name)
    except ValueError:
        pass
    try:
        return float(name)
    except ValueError:
        pass

    return _MISSING


def resolve_default_literal(symbol: Symbol) -> object:
    """Resolve a symbol as a literal, raising QyResolveError if unresolvable."""
    value = try_default_literal(symbol)
    if value is not _MISSING:
        return value
    from qy.errors import QyResolveError

    raise QyResolveError(
        f"unresolved symbol {symbol.name!r}",
        span=symbol.span,
        metadata={"symbol": symbol.name},
    )


def default_literal_type(symbol: Symbol) -> TypeName | None:
    """Return the TypeName for a symbol if it's a literal, else None."""
    name = symbol.name
    if is_string_literal(name):
        return "string"
    if is_char_literal(name):
        result = parse_char_literal(name)
        if result is not _MISSING:
            return "char"
        return None
    value = try_default_literal(symbol)
    if value is _MISSING:
        return None
    from qy.core.syntax import nil
    from qy.sem.core import NONE
    from qy.sem.core import T

    if value is nil:
        return "nil"
    if value is T:
        return "T"
    if value is NONE:
        return "none"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    return None
