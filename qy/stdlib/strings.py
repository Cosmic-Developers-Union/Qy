# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import PureOperator
from qy.evaluator import evaluate_async
from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import write_tuple
from qy.stdlib.module import StandardModule
from qy.values import QY_EMPTY_LIST
from qy.values import QyCons
from qy.values import iter_qy_list


def module() -> StandardModule:
    return StandardModule(
        "qy.str",
        {
            Symbol("str"): _text_operator("str", _str, "把值转换为文本 symbol。"),
            Symbol("str?"): _text_operator("str?", _str_predicate, "判断值是否为文本值。"),
            Symbol("str-len"): _text_operator("str-len", _str_len, "返回文本长度。"),
            Symbol("str-empty?"): _text_operator("str-empty?", _str_empty, "判断文本是否为空。"),
            Symbol("str-concat"): _text_operator("str-concat", _str_concat, "把多个值按文本拼接。"),
            Symbol("str-upper"): _text_operator("str-upper", _str_upper, "转换为大写文本。"),
            Symbol("str-lower"): _text_operator("str-lower", _str_lower, "转换为小写文本。"),
            Symbol("str-strip"): _text_operator("str-strip", _str_strip, "移除两端空白文本。"),
            Symbol("str-trim"): _text_operator("str-trim", _str_strip, "str-strip 的别名。"),
            Symbol("str-split"): _text_operator(
                "str-split", _str_split, "把文本拆分为 symbol tuple。"
            ),
            Symbol("str-join"): _text_operator("str-join", _str_join, "用分隔文本连接值。"),
            Symbol("str-replace"): _text_operator("str-replace", _str_replace, "替换文本。"),
            Symbol("str-contains?"): _text_operator(
                "str-contains?", _str_contains, "判断文本是否包含子文本。"
            ),
            Symbol("str-starts-with?"): _text_operator(
                "str-starts-with?", _str_starts_with, "判断文本是否以给定前缀开始。"
            ),
            Symbol("str-ends-with?"): _text_operator(
                "str-ends-with?", _str_ends_with, "判断文本是否以给定后缀结束。"
            ),
        },
    )


def _text_operator(name: str, func: Callable[..., object], doc: str) -> PureOperator:
    return PureOperator(name, func, doc, _evaluate_text_args)


async def _evaluate_text_args(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    return tuple([await _evaluate_text_arg(arg, env) for arg in args])


async def _evaluate_text_arg(expression: object, env: Environment) -> object:
    try:
        return await evaluate_async(expression, env)
    except EvaluationError:
        if isinstance(expression, Symbol):
            return expression
        raise


def _to_text(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, str):
        return value
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    if isinstance(value, tuple):
        try:
            return write_tuple(cast(TupleForm, value))
        except TypeError:
            return repr(value)
    return str(value)


def _to_symbol(text: str) -> Symbol:
    return Symbol(text)


def _str(value: object) -> Symbol:
    return _to_symbol(_to_text(value))


def _str_predicate(value: object) -> bool:
    return isinstance(value, Symbol | str)


def _str_len(value: object) -> int:
    return len(_to_text(value))


def _str_empty(value: object) -> bool:
    return _to_text(value) == ""


def _str_concat(*values: object) -> Symbol:
    return _to_symbol("".join(_to_text(value) for value in values))


def _str_upper(value: object) -> Symbol:
    return _to_symbol(_to_text(value).upper())


def _str_lower(value: object) -> Symbol:
    return _to_symbol(_to_text(value).lower())


def _str_strip(value: object) -> Symbol:
    return _to_symbol(_to_text(value).strip())


def _str_split(value: object, separator: object = None) -> tuple[Symbol, ...]:
    separator_text = None if separator is None else _to_text(separator)
    return tuple(_to_symbol(part) for part in _to_text(value).split(separator_text))


def _str_join(separator: object, values: object) -> Symbol:
    if values is QY_EMPTY_LIST or isinstance(values, QyCons):
        return _to_symbol(
            _to_text(separator).join(_to_text(value) for value in iter_qy_list(values))
        )
    if not isinstance(values, tuple | list):
        raise EvaluationError(
            f"str-join expects a list-like value as the second argument, got {values!r}"
        )
    return _to_symbol(_to_text(separator).join(_to_text(value) for value in values))


def _str_replace(value: object, old: object, new: object) -> Symbol:
    return _to_symbol(_to_text(value).replace(_to_text(old), _to_text(new)))


def _str_contains(value: object, needle: object) -> bool:
    return _to_text(needle) in _to_text(value)


def _str_starts_with(value: object, prefix: object) -> bool:
    return _to_text(value).startswith(_to_text(prefix))


def _str_ends_with(value: object, suffix: object) -> bool:
    return _to_text(value).endswith(_to_text(suffix))
