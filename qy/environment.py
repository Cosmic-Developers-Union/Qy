# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/core symbol-space + qy/session profile facts
"""Legacy Environment bridge to new symbol-space implementation.

This module provides backward compatibility by wrapping the new SymbolSpace
implementation. New code should use qy.core.SymbolSpace and qy.session.ProfileConfig
directly.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping

from qy.core.operator_signature import OperatorSignature
from qy.core.operators import ArgumentEvaluator
from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.symbol_space import ChainFrame as _ChainFrame
from qy.core.symbol_space import SymbolSpace
from qy.reader import Symbol
from qy.session.profile import LiteralResolver
from qy.session.profile import ProfileConfig

__all__ = ["ChainFrame", "Environment", "standard_environment"]

# Re-export ChainFrame for compatibility
ChainFrame = _ChainFrame


class Environment:
    """Legacy Environment wrapper around SymbolSpace.

    This class provides backward compatibility with the old Environment API
    while using the new SymbolSpace implementation internally.
    """

    def __init__(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        parent: Environment | None = None,
        literal_resolver: LiteralResolver | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> None:
        # Create underlying SymbolSpace
        parent_space = parent._space if parent is not None else None
        self._space = SymbolSpace(bindings, parent_space, name=name, writable=writable, lazy=lazy)

        # Store profile config for literal resolution
        if parent is not None:
            self._profile = parent._profile
        else:
            self._profile = ProfileConfig(literal_resolver)

    def resolve(self, symbol: Symbol) -> object:
        """Resolve a symbol to its value."""
        result = self._space.lookup(symbol)
        if result is not None:
            return result
        return self._profile.resolve_literal(symbol)

    def define(self, symbol: Symbol, value: object) -> object:
        """Define a symbol in this environment."""
        return self._space.define(symbol, value)

    def define_once(self, symbol: Symbol, value: object) -> object:
        """Define a symbol with once-complete semantics."""
        return self._space.define_once(symbol, value)

    def define_hidden(self, symbol: Symbol, value: object) -> object:
        """Define a hidden binding."""
        return self._space.define_hidden(symbol, value)

    def child(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> Environment:
        """Create a child environment."""
        return Environment(bindings, self, name=name, writable=writable, lazy=lazy)

    def fold_from(
        self,
        source: Mapping[Symbol, object],
        names: Iterable[Symbol],
    ) -> None:
        """Fold selected bindings from source into this environment."""
        self._space.fold_from(source, names)

    def pre_symbol_space_chain(self) -> tuple[ChainFrame, ...]:
        """Return the pre-symbol-space-chain as a tuple of ChainFrame nodes."""
        return self._space.chain().frames()

    @property
    def name(self) -> str:
        return self._space.name

    @property
    def writable(self) -> bool:
        return self._space.writable

    @property
    def lazy(self) -> bool:
        return self._space.lazy

    @property
    def literal_resolver(self) -> LiteralResolver:
        return self._profile.resolve_literal

    def bindings(self) -> dict[Symbol, object]:
        """Return all bindings including parent chain."""
        return self._space.all_bindings()

    def local_bindings(self) -> dict[Symbol, object]:
        """Return local bindings only."""
        return self._space.local_bindings()

    def hidden_bindings(self) -> dict[Symbol, object]:
        """Return hidden bindings."""
        result: dict[Symbol, object] = {}
        current: SymbolSpace | None = self._space
        while current is not None:
            result.update(current.hidden_bindings())
            current = current.parent
        return result

    def cache_lookup(self, key: object) -> object:
        """Look up a value in the cache."""
        return self._space.cache_lookup(key)

    def cache_define(self, key: object, value: object) -> object:
        """Define a value in the cache."""
        return self._space.cache_define(key, value)

    def cache_discard(self, key: object) -> None:
        """Remove a value from the cache."""
        self._space.cache_discard(key)

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
    """Create a standard environment with stdlib bindings.

    This is the legacy entry point. New code should use
    ProfileConfig.create_standard_space() instead.
    """
    profile = ProfileConfig(literal_resolver)
    space = profile.create_standard_space()

    # Wrap in Environment for backward compatibility
    env = Environment.__new__(Environment)
    env._space = space
    env._profile = profile
    return env
