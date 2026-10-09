# coding: utf-8
"""Qy library：用 Qy 语法（macro + quasiquote）定义的派生算子。.

原则：能由核心 form 组合出的能力，不要下沉成 host operator。这些派生算子以编译期
宏（MacroDefinition）形式注册到标准实例的 macro namespace，展开成
+ / - / < / = / mod / cond 等核心 form。宏展开尊重 lexical binding 遮蔽
（见 qy/macro/expand.py 的 shadowed_macros），因此 (let ((inc ...)) (inc 41))
会命中本地绑定而不是本模块的 inc 宏。

限制：本模块以**宏**实现，因此这些名字不能作为一等值使用（不能 apply/传入函数位置）；
需要一等派生函数时应改为运行时 Qy library（编译期 prelude 折进实例）而非宏。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qy.core.syntax import Symbol
from qy.core.syntax import list_to_chain as L

if TYPE_CHECKING:
    from qy.session.runtime_space import RuntimeSpace

__all__ = ["library_macros", "register_library_macros"]

_QUASIQUOTE = Symbol("quasiquote")
_UNQUOTE = Symbol("unquote")


def _uq(name: str) -> object:
    return L([_UNQUOTE, Symbol(name)])


def _qq(body: object) -> object:
    return L([_QUASIQUOTE, body])


def _call(name: str, *args: object) -> object:
    return L([Symbol(name), *args])


def library_macros() -> dict[str, tuple[tuple[str, ...], object]]:
    """返回派生算子的编译期宏定义：name -> (params, body form)。."""
    return {
        "inc": (("x",), _qq(_call("+", _uq("x"), Symbol("1")))),
        "dec": (("x",), _qq(_call("-", _uq("x"), Symbol("1")))),
        "zero?": (("x",), _qq(_call("=", _uq("x"), Symbol("0")))),
        "positive?": (("x",), _qq(_call("<", Symbol("0"), _uq("x")))),
        "negative?": (("x",), _qq(_call("<", _uq("x"), Symbol("0")))),
        "even?": (("x",), _qq(_call("=", _call("mod", _uq("x"), Symbol("2")), Symbol("0")))),
        "odd?": (("x",), _qq(_call("=", _call("mod", _uq("x"), Symbol("2")), Symbol("1")))),
        "abs": (
            ("x",),
            _qq(
                L(
                    [
                        Symbol("cond"),
                        L([_call("<", _uq("x"), Symbol("0")), _call("-", _uq("x"))]),
                        L([Symbol("true"), _uq("x")]),
                    ]
                )
            ),
        ),
        "min": (
            ("a", "b"),
            _qq(
                L(
                    [
                        Symbol("cond"),
                        L([_call("<", _uq("a"), _uq("b")), _uq("a")]),
                        L([Symbol("true"), _uq("b")]),
                    ]
                )
            ),
        ),
        "max": (
            ("a", "b"),
            _qq(
                L(
                    [
                        Symbol("cond"),
                        L([_call("<", _uq("a"), _uq("b")), _uq("b")]),
                        L([Symbol("true"), _uq("a")]),
                    ]
                )
            ),
        ),
    }


def register_library_macros(env: RuntimeSpace) -> None:
    """把派生算子注册到实例的 macro namespace（幂等）。."""
    from qy.macro import MacroDefinition
    from qy.macro.expand import _macro_namespace

    namespace = _macro_namespace(env)
    for name, (params, body) in library_macros().items():
        symbol = Symbol(name)
        namespace.setdefault(
            symbol,
            MacroDefinition(symbol, tuple(Symbol(param) for param in params), (body,), env),
        )
