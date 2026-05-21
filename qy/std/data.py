# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/std/*

from __future__ import annotations

from typing import cast

from qy.core.syntax import car as chain_car
from qy.core.syntax import cdr as chain_cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import cons as chain_cons
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.errors import QyArityError
from qy.errors import QyTypeError
from qy.operators import PureOperator
from qy.reader import Symbol
from qy.reader import get_span
from qy.values import QY_NIL
from qy.values import QY_T


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
    return is_nil(value) or is_chain(value)


def _proper_chain_items(value: object, context: str) -> tuple[object, ...]:
    try:
        return tuple(chain_to_list(value))
    except (TypeError, ValueError) as e:
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
    if is_chain(entry):
        tail = chain_cdr(entry)
        if not is_nil(tail) and not is_chain(tail):
            # Improper list: (key . value)
            return chain_car(entry), tail
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


def _atom(value: object) -> object:
    if is_nil(value):
        return QY_T
    if is_chain(value):
        return QY_NIL
    if not isinstance(value, tuple) or len(value) == 0:
        return QY_T
    return QY_NIL


def _is(left: object, right: object) -> object:
    return QY_T if left is right else QY_NIL


def _eq(left: object, right: object) -> object:
    if left is right:
        return QY_T
    if type(left) is not type(right):
        return QY_NIL
    if isinstance(left, int | float | str | bool | Symbol):
        return QY_T if left == right else QY_NIL
    return QY_NIL


def _reify(value: object) -> object:
    """Convert a runtime value to a syntax datum (Symbol or Chain)."""
    if value is QY_NIL:
        return Symbol("nil")
    if value is QY_T:
        return Symbol("T")
    if value is None:
        return Symbol("none")
    if isinstance(value, Symbol):
        return value
    if isinstance(value, int | float):
        return Symbol(str(value))
    if isinstance(value, str):
        return Symbol(value)
    if is_chain(value):
        items: list[object] = []
        node: object = value
        while is_chain(node):
            items.append(_reify(chain_car(node)))
            node = chain_cdr(node)
        if is_nil(node):
            return list_to_chain(items)
        # Improper list
        return list_to_chain([*items, Symbol("."), _reify(node)])
    return Symbol(repr(value))


def _type(value: object) -> Symbol:
    if value is QY_NIL:
        return Symbol("nil")
    if value is QY_T:
        return Symbol("T")
    if is_chain(value):
        return Symbol("chain")
    if isinstance(value, Symbol):
        return Symbol("symbol")
    return Symbol(type(value).__name__)


def _car(value: object) -> object:
    if is_nil(value):
        return QY_NIL
    if is_chain(value):
        return chain_car(value)
    raise QyTypeError(
        f"car expects a chain, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _cdr(value: object) -> object:
    if is_nil(value):
        return QY_NIL
    if is_chain(value):
        return chain_cdr(value)
    raise QyTypeError(
        f"cdr expects a chain, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _cons(head: object, tail: object) -> object:
    return chain_cons(head, tail)


def _append(left: object, right: object) -> object:
    left_items = _append_items(left)
    right_items = _append_items(right)
    combined = left_items + right_items
    if is_chain(left) or is_nil(left):
        return list_to_chain(combined)
    if is_chain(right) or is_nil(right):
        return list_to_chain(combined)
    return combined


def _append_items(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if is_nil(value):
        return ()
    if is_chain(value):
        return _proper_chain_items(value, "append")
    raise QyTypeError(
        f"append expects tuple/list/chain inputs, got {value!r}",
        span=get_span(value),
        metadata={"value": value},
    )


def _chain(value: object) -> object:
    if is_nil(value) or is_chain(value):
        return value
    if isinstance(value, list | tuple):
        return list_to_chain(value)
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


def _tuple_predicate(value: object) -> object:
    return QY_T if isinstance(value, tuple) else QY_NIL


def _list_predicate(value: object) -> object:
    return QY_T if isinstance(value, list) else QY_NIL


def _dict_predicate(value: object) -> object:
    return QY_T if isinstance(value, dict) else QY_NIL


def _set_predicate(value: object) -> object:
    return QY_T if isinstance(value, set) else QY_NIL


def _len(value: object) -> int:
    if isinstance(value, Symbol):
        return len(value.name)
    if is_nil(value):
        return 0
    if is_chain(value):
        try:
            return len(chain_to_list(value))
        except (TypeError, ValueError) as e:
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
    if is_nil(collection):
        return default
    if is_chain(collection):
        index = _ensure_index(key)
        try:
            return chain_to_list(collection)[index]
        except (IndexError, TypeError, ValueError):
            return default
    raise QyTypeError(
        f"get expects a chain, tuple, list, or dict, got {collection!r}",
        span=get_span(collection),
        metadata={"collection": collection},
    )


def _has(*args: object) -> object:
    if len(args) != 2:
        raise QyArityError(
            f"has? expects exactly two arguments, got {len(args)}",
            metadata={"expected": 2, "actual": len(args)},
        )
    collection, key = args
    if isinstance(collection, dict):
        try:
            return QY_T if key in collection else QY_NIL
        except TypeError:
            return QY_NIL
    if isinstance(collection, set):
        try:
            return QY_T if key in collection else QY_NIL
        except TypeError:
            return QY_NIL
    if isinstance(collection, tuple | list):
        index = _ensure_index(key)
        return QY_T if -len(collection) <= index < len(collection) else QY_NIL
    if is_nil(collection):
        return QY_NIL
    if is_chain(collection):
        index = _ensure_index(key)
        try:
            length = len(chain_to_list(collection))
        except (TypeError, ValueError):
            return QY_NIL
        return QY_T if -length <= index < length else QY_NIL
    raise QyTypeError(
        f"has? expects a chain, tuple, list, dict, or set, got {collection!r}",
        span=get_span(collection),
        metadata={"collection": collection},
    )


def python_container_operators() -> dict[Symbol, object]:
    return {
        Symbol("dict"): PureOperator("dict", _dict, "把 key/value 参数转换为 Python dict。"),
        Symbol("dict?"): PureOperator("dict?", _dict_predicate, "判断值是否为 dict。"),
        Symbol("list"): PureOperator("list", _list, "把参数转换为 Python list。"),
        Symbol("list?"): PureOperator("list?", _list_predicate, "判断值是否为 list。"),
        Symbol("set"): PureOperator("set", _set, "把参数转换为 Python set。"),
        Symbol("set?"): PureOperator("set?", _set_predicate, "判断值是否为 set。"),
        Symbol("tuple"): PureOperator("tuple", _tuple, "把参数转换为 Python tuple。"),
        Symbol("tuple?"): PureOperator("tuple?", _tuple_predicate, "判断值是否为 tuple。"),
    }


def operators() -> dict[Symbol, object]:
    return {
        Symbol("atom"): PureOperator("atom", _atom, "如果值不是非空 chain 或 tuple，则返回 true。"),
        Symbol("car"): PureOperator("car", _car, "返回 chain 的第一个元素。"),
        Symbol("cdr"): PureOperator("cdr", _cdr, "返回 chain 除第一个元素外的剩余部分。"),
        Symbol("chain"): PureOperator("chain", _chain, "把 Python list/tuple 转换为 Qy chain。"),
        Symbol("append"): PureOperator(
            "append", _append, "拼接 tuple/list/chain，并在 chain 场景返回 chain。"
        ),
        Symbol("cons"): PureOperator(
            "cons", _cons, "构造 chain cell；对 Python tuple/list 保持同类拼接。"
        ),
        Symbol("eq"): PureOperator(
            "eq", _eq, "Lisp 风格 eq；atom 按值比较，chain 按 identity 比较。"
        ),
        Symbol("reify"): PureOperator("reify", _reify, "将 runtime 值转为 syntax datum。"),
        Symbol("get"): PureOperator("get", _get, "从 chain/tuple/list/dict 获取项。"),
        Symbol("has?"): PureOperator("has?", _has, "判断 collection 是否包含 key、index 或成员。"),
        Symbol("is"): PureOperator("is", _is, "按 Python is 语义比较 identity。"),
        Symbol("len"): PureOperator("len", _len, "返回 collection 长度。"),
        Symbol("type"): PureOperator("type", _type, "返回值的类型名称。"),
        Symbol("true"): QY_T,
        Symbol("false"): QY_NIL,
        Symbol("T"): QY_T,
        Symbol("nil"): QY_NIL,
        Symbol("none"): None,
    }
