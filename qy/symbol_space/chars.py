# coding: utf-8

from __future__ import annotations

from qy.core.operators import PureOperator
from qy.core.syntax import nil as QY_NIL
from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule
from qy.sem.core import CharValue
from qy.sem.core import IntValue
from qy.sem.core import StringValue
from qy.sem.core import T as QY_T


def module() -> StandardModule:
    return StandardModule(
        "qy.char",
        {
            Symbol("char?"): PureOperator("char?", _char_predicate),
            Symbol("char=?"): PureOperator("char=?", _char_eq),
            Symbol("char<?"): PureOperator("char<?", _char_lt),
            Symbol("char<=?"): PureOperator("char<=?", _char_le),
            Symbol("char>?"): PureOperator("char>?", _char_gt),
            Symbol("char>=?"): PureOperator("char>=?", _char_ge),
            Symbol("char->integer"): PureOperator("char->integer", _char_to_integer),
            Symbol("integer->char"): PureOperator("integer->char", _integer_to_char),
            Symbol("char-alphabetic?"): PureOperator("char-alphabetic?", _char_alphabetic),
            Symbol("char-numeric?"): PureOperator("char-numeric?", _char_numeric),
            Symbol("char-whitespace?"): PureOperator("char-whitespace?", _char_whitespace),
            Symbol("char-upper-case?"): PureOperator("char-upper-case?", _char_upper_case),
            Symbol("char-lower-case?"): PureOperator("char-lower-case?", _char_lower_case),
            Symbol("char-upcase"): PureOperator("char-upcase", _char_upcase),
            Symbol("char-downcase"): PureOperator("char-downcase", _char_downcase),
            Symbol("char->string"): PureOperator("char->string", _char_to_string),
        },
    )


def _require_char(value: object, op: str = "") -> CharValue:
    if isinstance(value, CharValue):
        return value
    raise TypeError(f"{op}: expected char, got {type(value).__name__}")


def _char_predicate(value: object) -> object:
    return QY_T if isinstance(value, CharValue) else QY_NIL


def _char_eq(a: object, b: object) -> object:
    return QY_T if _require_char(a, "char=?").value == _require_char(b, "char=?").value else QY_NIL


def _char_lt(a: object, b: object) -> object:
    return QY_T if _require_char(a, "char<?").value < _require_char(b, "char<?").value else QY_NIL


def _char_le(a: object, b: object) -> object:
    return (
        QY_T if _require_char(a, "char<=?").value <= _require_char(b, "char<=?").value else QY_NIL
    )


def _char_gt(a: object, b: object) -> object:
    return QY_T if _require_char(a, "char>?").value > _require_char(b, "char>?").value else QY_NIL


def _char_ge(a: object, b: object) -> object:
    return (
        QY_T if _require_char(a, "char>=?").value >= _require_char(b, "char>=?").value else QY_NIL
    )


def _char_to_integer(c: object) -> IntValue:
    return IntValue(ord(_require_char(c, "char->integer").value))


def _integer_to_char(n: object) -> CharValue:
    if isinstance(n, IntValue):
        code = n.value
    elif isinstance(n, int):
        code = n
    else:
        raise TypeError(f"integer->char: expected integer, got {type(n).__name__}")
    try:
        return CharValue(chr(code))
    except (ValueError, OverflowError) as e:
        raise ValueError(f"integer->char: invalid codepoint {code}") from e


def _char_alphabetic(c: object) -> object:
    return QY_T if _require_char(c, "char-alphabetic?").value.isalpha() else QY_NIL


def _char_numeric(c: object) -> object:
    return QY_T if _require_char(c, "char-numeric?").value.isdigit() else QY_NIL


def _char_whitespace(c: object) -> object:
    return QY_T if _require_char(c, "char-whitespace?").value.isspace() else QY_NIL


def _char_upper_case(c: object) -> object:
    return QY_T if _require_char(c, "char-upper-case?").value.isupper() else QY_NIL


def _char_lower_case(c: object) -> object:
    return QY_T if _require_char(c, "char-lower-case?").value.islower() else QY_NIL


def _char_upcase(c: object) -> CharValue:
    return CharValue(_require_char(c, "char-upcase").value.upper())


def _char_downcase(c: object) -> CharValue:
    return CharValue(_require_char(c, "char-downcase").value.lower())


def _char_to_string(c: object) -> StringValue:
    return StringValue(_require_char(c, "char->string").value)
