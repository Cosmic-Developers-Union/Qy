# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping

from qy.literals import resolve_default_literal
from qy.operator_signature import OperatorSignature
from qy.operators import ArgumentEvaluator
from qy.operators import ControlOperator
from qy.operators import EffectOperator
from qy.operators import MetaOperator
from qy.operators import PureOperator
from qy.operators import ScopeOperator
from qy.reader import Symbol

__all__ = ["Environment", "standard_environment"]

LiteralResolver = Callable[[Symbol], object]


class Environment:
    def __init__(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        parent: Environment | None = None,
        literal_resolver: LiteralResolver | None = None,
    ) -> None:
        self._bindings = dict(bindings or {})
        self._parent = parent
        self._cache: dict[object, object] = parent._cache if parent is not None else {}
        self._hidden: dict[Symbol, object] = {}
        if parent is not None:
            self._literal_resolver = parent._literal_resolver
        else:
            self._literal_resolver: LiteralResolver = literal_resolver or resolve_default_literal

    def resolve(self, symbol: Symbol) -> object:
        if symbol in self._bindings:
            return self._bindings[symbol]
        if symbol in self._hidden:
            return self._hidden[symbol]
        if self._parent is not None:
            return self._parent.resolve(symbol)
        return self._literal_resolver(symbol)

    def define(self, symbol: Symbol, value: object) -> object:
        self._bindings[symbol] = value
        return value

    def define_once(self, symbol: Symbol, value: object) -> object:
        if symbol in self._bindings:
            from qy.errors import QyRuntimeError

            raise QyRuntimeError(
                f"symbol {symbol.name!r} is already bound in this scope; use 'let' to shadow"
            )
        self._bindings[symbol] = value
        return value

    def define_hidden(self, symbol: Symbol, value: object) -> object:
        self._hidden[symbol] = value
        return value

    def child(self, bindings: Mapping[Symbol, object] | None = None) -> Environment:
        return Environment(bindings, self)

    @property
    def literal_resolver(self) -> LiteralResolver:
        return self._literal_resolver

    def bindings(self) -> dict[Symbol, object]:
        if self._parent is None:
            return dict(self._bindings)
        result = self._parent.bindings()
        result.update(self._bindings)
        return result

    def local_bindings(self) -> dict[Symbol, object]:
        return dict(self._bindings)

    def hidden_bindings(self) -> dict[Symbol, object]:
        if self._parent is None:
            return dict(self._hidden)
        result = self._parent.hidden_bindings()
        result.update(self._hidden)
        return result

    def cache_lookup(self, key: object) -> object:
        return self._cache[key]

    def cache_define(self, key: object, value: object) -> object:
        self._cache[key] = value
        return value

    def cache_discard(self, key: object) -> None:
        self._cache.pop(key, None)

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
        argument_evaluator: ArgumentEvaluator | None = None,
        signature: OperatorSignature | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | Callable[..., object]:
        def register(func: Callable[..., object]) -> Callable[..., object]:
            self.define(Symbol(name), PureOperator(name, func, doc, argument_evaluator, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_scope(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        def register(
            func: Callable[[tuple[object, ...], Environment], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), ScopeOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_control(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        def register(
            func: Callable[[tuple[object, ...], Environment], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), ControlOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_effect(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        def register(
            func: Callable[[tuple[object, ...], Environment], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), EffectOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_meta(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        def register(
            func: Callable[[tuple[object, ...], Environment], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), MetaOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_evaluation(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        return self.register_control(name, func, doc=doc, signature=signature)

    def register_syntax(
        self,
        name: str,
        func: Callable[[tuple[object, ...], Environment], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], Environment], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        return self.register_meta(name, func, doc=doc, signature=signature)


def standard_environment(*, literal_resolver: LiteralResolver | None = None) -> Environment:
    from qy.stdlib import standard_bindings

    return Environment(standard_bindings(), literal_resolver=literal_resolver)
