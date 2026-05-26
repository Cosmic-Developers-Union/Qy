# coding: utf-8
"""String stdlib module (qy.str).

Operators follow the target API from docs/stdlib-operators.md.
Internally accepts both Python str and StringValue as string inputs
during the transition period. Outputs StringValue where applicable.
"""

from __future__ import annotations

from qy.core.operators import PureOperator
from qy.core.syntax import nil as QY_NIL
from qy.errors import EvaluationError
from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule
from qy.sem.core import CharValue
from qy.sem.core import IntValue
from qy.sem.core import StringValue
from qy.sem.core import T as QY_T


def module() -> StandardModule:
    return StandardModule(
        "qy.str",
        {
            Symbol("string?"): PureOperator("string?", _string_predicate),
            Symbol("string-length"): PureOperator("string-length", _string_length),
            Symbol("string-concat"): PureOperator("string-concat", _string_concat),
            Symbol("string="): PureOperator("string=", _string_eq),
            Symbol("string-slice"): PureOperator("string-slice", _string_slice),
            Symbol("string-at"): PureOperator("string-at", _string_at),
            Symbol("string-find"): PureOperator("string-find", _string_find),
            Symbol("string-split"): PureOperator("string-split", _string_split),
            Symbol("string-join"): PureOperator("string-join", _string_join),
            Symbol("string-replace"): PureOperator("string-replace", _string_replace),
            Symbol("string-empty?"): PureOperator("string-empty?", _string_empty),
            Symbol("string-starts-with?"): PureOperator("string-starts-with?", _string_starts_with),
            Symbol("string-ends-with?"): PureOperator("string-ends-with?", _string_ends_with),
            Symbol("string-contains?"): PureOperator("string-contains?", _string_contains),
            Symbol("string-upper"): PureOperator("string-upper", _string_upper),
            Symbol("string-lower"): PureOperator("string-lower", _string_lower),
            Symbol("string-trim"): PureOperator("string-trim", _string_trim),
            Symbol("string->list"): PureOperator("string->list", _string_to_list),
            Symbol("string->symbol"): PureOperator("string->symbol", _string_to_symbol),
            Symbol("symbol->string"): PureOperator("symbol->string", _symbol_to_string),
        },
    )


def _extract_str(value: object, op: str = "") -> str:
    if isinstance(value, StringValue):
        return value.value
    if isinstance(value, str):
        return value
    if isinstance(value, Symbol):
        return value.name
    raise TypeError(f"{op}: expected string, got {type(value).__name__}")


def _extract_int(value: object, op: str = "") -> int:
    if isinstance(value, IntValue):
        return value.value
    if isinstance(value, int):
        return value
    raise TypeError(f"{op}: expected integer, got {type(value).__name__}")


def _string_predicate(value: object) -> object:
    return QY_T if isinstance(value, StringValue | str) else QY_NIL


def _string_length(s: object) -> IntValue:
    return IntValue(len(_extract_str(s, "string-length")))


def _string_concat(*values: object) -> StringValue:
    return StringValue("".join(_extract_str(v, "string-concat") for v in values))


def _string_eq(a: object, b: object) -> object:
    return QY_T if _extract_str(a, "string=") == _extract_str(b, "string=") else QY_NIL


def _string_slice(s: object, start: object, end: object = None) -> StringValue:
    text = _extract_str(s, "string-slice")
    i = _extract_int(start, "string-slice")
    if end is None:
        return StringValue(text[i:])
    j = _extract_int(end, "string-slice")
    return StringValue(text[i:j])


def _string_at(s: object, index: object) -> CharValue:
    text = _extract_str(s, "string-at")
    i = _extract_int(index, "string-at")
    if i < 0 or i >= len(text):
        raise EvaluationError(f"string-at: index {i} out of range for string of length {len(text)}")
    return CharValue(text[i])


def _string_find(s: object, needle: object) -> object:
    text = _extract_str(s, "string-find")
    sub = _extract_str(needle, "string-find")
    idx = text.find(sub)
    if idx == -1:
        return QY_NIL
    return IntValue(idx)


def _string_split(s: object, separator: object = None) -> tuple[StringValue, ...]:
    text = _extract_str(s, "string-split")
    if separator is None:
        parts = text.split()
    else:
        parts = text.split(_extract_str(separator, "string-split"))
    return tuple(StringValue(p) for p in parts)


def _string_join(separator: object, *values: object) -> StringValue:
    sep = _extract_str(separator, "string-join")
    parts: list[str] = []
    for v in values:
        if isinstance(v, tuple):
            parts.extend(_extract_str(item, "string-join") for item in v)
        else:
            parts.append(_extract_str(v, "string-join"))
    return StringValue(sep.join(parts))


def _string_replace(s: object, old: object, new: object) -> StringValue:
    text = _extract_str(s, "string-replace")
    return StringValue(
        text.replace(_extract_str(old, "string-replace"), _extract_str(new, "string-replace"))
    )


def _string_empty(s: object) -> object:
    return QY_T if _extract_str(s, "string-empty?") == "" else QY_NIL


def _string_starts_with(s: object, prefix: object) -> object:
    return (
        QY_T
        if _extract_str(s, "string-starts-with?").startswith(
            _extract_str(prefix, "string-starts-with?")
        )
        else QY_NIL
    )


def _string_ends_with(s: object, suffix: object) -> object:
    return (
        QY_T
        if _extract_str(s, "string-ends-with?").endswith(_extract_str(suffix, "string-ends-with?"))
        else QY_NIL
    )


def _string_contains(s: object, needle: object) -> object:
    return (
        QY_T
        if _extract_str(needle, "string-contains?") in _extract_str(s, "string-contains?")
        else QY_NIL
    )


def _string_upper(s: object) -> StringValue:
    return StringValue(_extract_str(s, "string-upper").upper())


def _string_lower(s: object) -> StringValue:
    return StringValue(_extract_str(s, "string-lower").lower())


def _string_trim(s: object) -> StringValue:
    return StringValue(_extract_str(s, "string-trim").strip())


def _string_to_list(s: object) -> tuple[CharValue, ...]:
    return tuple(CharValue(c) for c in _extract_str(s, "string->list"))


def _string_to_symbol(s: object) -> Symbol:
    return Symbol(_extract_str(s, "string->symbol"))


def _symbol_to_string(s: object) -> StringValue:
    if isinstance(s, Symbol):
        return StringValue(s.name)
    raise TypeError(f"symbol->string: expected symbol, got {type(s).__name__}")
