# coding: utf-8

from __future__ import annotations

from typing import cast

from qy.errors import QyArityError
from qy.errors import QyTypeError
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import PureOperator
from qy.evaluator import evaluate_async
from qy.reader import Symbol
from qy.reader import get_span
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyCons
from qy.values import list_to_qy_cons
from qy.values import qy_cons_to_tuple


def _ensure_tuple(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise QyTypeError(
            f"expected tuple, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )
    return value


def _ensure_sequence(value: object) -> tuple[object, ...] | list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    if not isinstance(value, tuple):
        raise QyTypeError(
            f"expected tuple or list, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )
    return value


def _ensure_index(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QyTypeError(
            f"expected integer index, got {value!r}",
            span=get_span(value),
            metadata={"value": value},
        )
    return value


def _is_qy_chain(value: object) -> bool:
    return value is QY_EMPTY_LIST or isinstance(value, QyCons)


def _proper_chain_items(value: object, context: str) -> tuple[object, ...]:
    try:
        return qy_cons_to_tuple(value)
    except TypeError as e:
        raise QyTypeError(f"{context} expects a proper Qy chain", cause=e) from e


def _dict_from_chain(value: object) -> dict[object, object]:
    result: dict[object, object] = {}
    for entry in _proper_chain_items(value, "dict"):
        key, item = _dict_entry_pair(entry)
        try:
            result[key] = item
        except TypeError as e:
            raise QyTypeError(
                f"dict key must be hashable, got {key!r}",
                span=get_span(key),
                cause=e,
                metadata={"key": key},
            ) from e
    return result


def _dict_entry_pair(entry: object) -> tuple[object, object]:
    if isinstance(entry, QyCons):
        if entry.tail is not QY_EMPTY_LIST and not isinstance(entry.tail, QyCons):
            return entry.head, entry.tail
        items = _proper_chain_items(entry, "dict entry")
    elif isinstance(entry, tuple | list):
        items = tuple(entry)
    else:
        raise QyTypeError(
            f"dict chain entry must be a pair, got {entry!r}",
            span=get_span(entry),
            metadata={"entry": entry},
        )
    if len(items) != 2:
        raise QyTypeError(
            f"dict chain entry must contain two values, got {len(items)}",
            span=get_span(entry),
            metadata={"entry": entry},
        )
    return items[0], items[1]


async def _evaluate_data_args(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    return tuple([await _evaluate_data_arg(arg, env) for arg in args])


async def _evaluate_lookup_args(args: tuple[object, ...], env: Environment) -> tuple[object, ...]:
    if not args:
        return ()
    collection = await evaluate_async(args[0], env)
    rest = tuple([await _evaluate_data_arg(arg, env) for arg in args[1:]])
    return (collection, *rest)


async def _evaluate_data_arg(expression: object, env: Environment) -> object:
    try:
        return await evaluate_async(expression, env)
    except EvaluationError:
        if isinstance(expression, Symbol):
            return expression
        raise


def _atom(value: object) -> bool:
    if value is QY_EMPTY_LIST:
        return True
    if isinstance(value, QyCons):
        return False
    return not isinstance(value, tuple) or len(value) == 0


def _is(left: object, right: object) -> bool:
    return left is right


def _eq(left: object, right: object) -> bool:
    if left is QY_NIL or right is QY_NIL:
        return left is QY_NIL and right is QY_NIL
    if left is QY_T or right is QY_T:
        return left is QY_T and right is QY_T
    if isinstance(left, QyCons) or isinstance(right, QyCons):
        return left is right
    if isinstance(left, Symbol) or isinstance(right, Symbol):
        return isinstance(left, Symbol) and isinstance(right, Symbol) and left.name == right.name
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return left == right
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == 0 and len(right) == 0
    return left is right


def _type(value: object) -> Symbol:
    if value is QY_NIL:
        return Symbol("nil")
    if value is QY_T:
        return Symbol("T")
    if isinstance(value, QyCons):
        return Symbol("chain")
    if isinstance(value, Symbol):
        return Symbol("symbol")
    return Symbol(type(value).__name__)


def _car(value: object) -> object:
    if value is QY_NIL:
        return QY_NIL
    if isinstance(value, QyCons):
        return value.head
    raise QyTypeError(
        f"car expects a chain, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _cdr(value: object) -> object:
    if value is QY_NIL:
        return QY_NIL
    if isinstance(value, QyCons):
        return value.tail
    raise QyTypeError(
        f"cdr expects a chain, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _cons(head: object, tail: object) -> object:
    return QyCons(head, tail)


def _chain(value: object) -> object:
    if value is QY_NIL or isinstance(value, QyCons):
        return value
    if isinstance(value, list | tuple):
        return list_to_qy_cons(value)
    raise QyTypeError(
        f"chain expects a Python list or tuple, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _tuple(*args: object) -> tuple[object, ...]:
    if len(args) == 1 and _is_qy_chain(args[0]):
        return _proper_chain_items(args[0], "tuple")
    return tuple(args)


def _list(*args: object) -> list[object]:
    if len(args) == 1 and _is_qy_chain(args[0]):
        return list(_proper_chain_items(args[0], "list"))
    return list(args)


def _dict(*args: object) -> dict[object, object]:
    if len(args) == 1 and _is_qy_chain(args[0]):
        return _dict_from_chain(args[0])
    if len(args) % 2 != 0:
        raise QyArityError(
            f"dict expects key/value pairs, got {len(args)} argument(s)",
            metadata={"actual": len(args)},
        )
    result: dict[object, object] = {}
    for index in range(0, len(args), 2):
        key = args[index]
        value = args[index + 1]
        try:
            result[key] = value
        except TypeError as e:
            raise QyTypeError(
                f"dict key must be hashable, got {key!r}",
                span=get_span(key),
                cause=e,
                metadata={"key": key},
            ) from e
    return result


def _set(*args: object) -> set[object]:
    values = (
        _proper_chain_items(args[0], "set") if len(args) == 1 and _is_qy_chain(args[0]) else args
    )
    result: set[object] = set()
    for value in values:
        try:
            result.add(value)
        except TypeError as e:
            raise QyTypeError(
                f"set item must be hashable, got {value!r}",
                span=get_span(value),
                cause=e,
                metadata={"value": value},
            ) from e
    return result


def _tuple_predicate(value: object) -> bool:
    return isinstance(value, tuple)


def _list_predicate(value: object) -> bool:
    return isinstance(value, list)


def _dict_predicate(value: object) -> bool:
    return isinstance(value, dict)


def _set_predicate(value: object) -> bool:
    return isinstance(value, set)


def _len(value: object) -> int:
    if isinstance(value, Symbol):
        return len(value.name)
    if value is QY_EMPTY_LIST:
        return 0
    if isinstance(value, QyCons):
        try:
            return len(qy_cons_to_tuple(value))
        except TypeError as e:
            raise QyTypeError("len expects a proper Qy chain", cause=e) from e
    if isinstance(value, str | tuple | list | dict | set):
        return len(value)
    raise QyTypeError(
        f"len expects a collection, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _get(collection: object, key: object, *default_values: object) -> object:
    if len(default_values) > 1:
        raise QyArityError(
            f"get expects two or three arguments, got {len(default_values) + 2}",
            metadata={"expected": "2..3", "actual": len(default_values) + 2},
        )
    default = default_values[0] if default_values else None
    if isinstance(collection, dict):
        mapping = cast(dict[object, object], collection)
        try:
            return mapping[key]
        except (KeyError, TypeError):
            return default
    if isinstance(collection, tuple | list):
        index = _ensure_index(key)
        try:
            return collection[index]
        except IndexError:
            return default
    if collection is QY_EMPTY_LIST:
        return default
    if isinstance(collection, QyCons):
        index = _ensure_index(key)
        try:
            return qy_cons_to_tuple(collection)[index]
        except (IndexError, TypeError):
            return default
    raise QyTypeError(
        f"get expects a chain, tuple, list, or dict, got {collection!r}",
        span=get_span(collection),
        metadata={"collection": collection},
    )


def _has(*args: object) -> bool:
    if len(args) != 2:
        raise QyArityError(
            f"has? expects exactly two arguments, got {len(args)}",
            metadata={"expected": 2, "actual": len(args)},
        )
    collection, key = args
    if isinstance(collection, dict):
        try:
            return key in collection
        except TypeError:
            return False
    if isinstance(collection, set):
        try:
            return key in collection
        except TypeError:
            return False
    if isinstance(collection, tuple | list):
        index = _ensure_index(key)
        return -len(collection) <= index < len(collection)
    if collection is QY_EMPTY_LIST:
        return False
    if isinstance(collection, QyCons):
        index = _ensure_index(key)
        try:
            length = len(qy_cons_to_tuple(collection))
        except TypeError:
            return False
        return -length <= index < length
    raise QyTypeError(
        f"has? expects a chain, tuple, list, dict, or set, got {collection!r}",
        span=get_span(collection),
        metadata={"collection": collection},
    )


def operators() -> dict[Symbol, object]:
    return {
        Symbol("atom"): PureOperator("atom", _atom, "如果值不是非空 chain 或 tuple，则返回 true。"),
        Symbol("car"): PureOperator("car", _car, "返回 chain 的第一个元素。"),
        Symbol("cdr"): PureOperator("cdr", _cdr, "返回 chain 除第一个元素外的剩余部分。"),
        Symbol("chain"): PureOperator("chain", _chain, "把 Python list/tuple 转换为 Qy chain。"),
        Symbol("cons"): PureOperator(
            "cons", _cons, "构造 chain cell；对 Python tuple/list 保持同类拼接。"
        ),
        Symbol("dict"): PureOperator(
            "dict", _dict, "把 key/value 参数转换为 Python dict。", _evaluate_data_args
        ),
        Symbol("dict?"): PureOperator("dict?", _dict_predicate, "判断值是否为 dict。"),
        Symbol("eq"): PureOperator("eq", _eq, "Lisp 风格 eq；chain 按 identity 比较。"),
        Symbol("get"): PureOperator(
            "get", _get, "从 chain/tuple/list/dict 获取项。", _evaluate_lookup_args
        ),
        Symbol("has?"): PureOperator(
            "has?",
            _has,
            "判断 collection 是否包含 key、index 或成员。",
            _evaluate_lookup_args,
        ),
        Symbol("is"): PureOperator("is", _is, "按 Python is 语义比较 identity。"),
        Symbol("len"): PureOperator("len", _len, "返回 collection 长度。"),
        Symbol("list"): PureOperator(
            "list", _list, "把参数转换为 Python list。", _evaluate_data_args
        ),
        Symbol("list?"): PureOperator("list?", _list_predicate, "判断值是否为 list。"),
        Symbol("set"): PureOperator("set", _set, "把参数转换为 Python set。", _evaluate_data_args),
        Symbol("set?"): PureOperator("set?", _set_predicate, "判断值是否为 set。"),
        Symbol("tuple"): PureOperator(
            "tuple", _tuple, "把参数转换为 Python tuple。", _evaluate_data_args
        ),
        Symbol("tuple?"): PureOperator("tuple?", _tuple_predicate, "判断值是否为 tuple。"),
        Symbol("type"): PureOperator("type", _type, "返回值的类型名称。"),
        Symbol("true"): True,
        Symbol("false"): False,
        Symbol("T"): QY_T,
        Symbol("nil"): QY_NIL,
        Symbol("none"): None,
    }
