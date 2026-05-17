# coding: utf-8

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass

from qy.literals import resolve_default_literal
from qy.operator_signature import OperatorSignature
from qy.operators import ArgumentEvaluator
from qy.operators import ControlOperator
from qy.operators import EffectOperator
from qy.operators import MetaOperator
from qy.operators import PureOperator
from qy.operators import ScopeOperator
from qy.reader import Symbol

__all__ = ["Environment", "EnvironmentFrame", "standard_environment"]

LiteralResolver = Callable[[Symbol], object]


@dataclass(frozen=True, slots=True)
class EnvironmentFrame:
    bindings: dict[Symbol, object]
    hidden_bindings: dict[Symbol, object]


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

    def fold_from(
        self,
        source: Mapping[Symbol, object],
        names: Iterable[Symbol],
    ) -> None:
        """Fold selected bindings from *source* into this environment.

        This is the formal fold operation: it absorbs visible bindings from an
        external source (e.g. a module's export view) into the local
        symbol-space, making them local members.  ``define_once`` semantics
        apply — attempting to fold a name that already exists in the current
        scope raises ``QyRuntimeError``, mirroring ``define`` behaviour.
        """
        from qy.errors import QyRuntimeError

        for name in names:
            if name in self._bindings:
                raise QyRuntimeError(
                    f"symbol {name.name!r} is already bound in this scope; use 'let' to shadow"
                )
            if name not in source:
                raise QyRuntimeError(f"source has no export {name.name!r}")
            self._bindings[name] = source[name]

    def pre_symbol_space_chain(self) -> tuple[EnvironmentFrame, ...]:
        frame = EnvironmentFrame(self.local_bindings(), self.hidden_bindings())
        if self._parent is None:
            return (frame,)
        return (*self._parent.pre_symbol_space_chain(), frame)

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
    from qy.stdlib import standard_profile_bindings

    return Environment(standard_profile_bindings(), literal_resolver=literal_resolver)
