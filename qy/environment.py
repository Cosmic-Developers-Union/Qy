# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/core symbol-space + qy/session profile facts
"""Legacy Environment bridge to new RuntimeSpace implementation.

This module provides backward compatibility by wrapping the new RuntimeSpace
implementation. New code should use qy.session.RuntimeSpace directly.

DEPRECATED: This module will be removed after all code is migrated to RuntimeSpace.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping

from qy.core.operator_signature import OperatorSignature
from qy.core.operators import ArgumentEvaluator
from qy.core.symbol_space import ChainFrame as _ChainFrame
from qy.core.symbol_space import SymbolSpace
from qy.frontend.reader import Symbol
from qy.session.profile import LiteralResolver
from qy.session.runtime_space import RuntimeSpace

__all__ = ["ChainFrame", "Environment", "standard_environment"]

# Re-export ChainFrame for compatibility
ChainFrame = _ChainFrame


class Environment:
    """Legacy Environment wrapper around RuntimeSpace.

    This class provides backward compatibility with the old Environment API
    while using the new RuntimeSpace implementation internally.

    DEPRECATED: Use qy.session.RuntimeSpace directly in new code.
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
        # Create underlying RuntimeSpace
        if parent is not None:
            # Child environment: create child space
            parent_runtime = parent._runtime
            child_space = parent_runtime.space.child(
                bindings, name=name, writable=writable, lazy=lazy
            )
            self._runtime = RuntimeSpace(child_space, parent_runtime.profile)
        else:
            # Root environment: create new space with profile
            from qy.session.profile import ProfileConfig

            profile = ProfileConfig(literal_resolver)
            if bindings:
                space = SymbolSpace(bindings, name=name, writable=writable, lazy=lazy)
            else:
                space = SymbolSpace(name=name, writable=writable, lazy=lazy)
            self._runtime = RuntimeSpace(space, profile)

    def resolve(self, symbol: Symbol) -> object:
        """Resolve a symbol to its value."""
        return self._runtime.resolve(symbol)

    def define(self, symbol: Symbol, value: object) -> object:
        """Define a symbol in this environment."""
        return self._runtime.define(symbol, value)

    def define_once(self, symbol: Symbol, value: object) -> object:
        """Define a symbol with once-complete semantics."""
        return self._runtime.define_once(symbol, value)

    def define_hidden(self, symbol: Symbol, value: object) -> object:
        """Define a hidden binding."""
        return self._runtime.define_hidden(symbol, value)

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
        self._runtime.space.fold_from(source, names)

    def pre_symbol_space_chain(self) -> tuple[ChainFrame, ...]:
        """Return the pre-symbol-space-chain as a tuple of ChainFrame nodes."""
        return self._runtime.space.chain().frames()

    @property
    def name(self) -> str:
        return self._runtime.space.name

    @property
    def writable(self) -> bool:
        return self._runtime.space.writable

    @property
    def lazy(self) -> bool:
        return self._runtime.space.lazy

    @property
    def literal_resolver(self) -> LiteralResolver:
        return self._runtime.profile.resolve_literal

    def bindings(self) -> dict[Symbol, object]:
        """Return all bindings including parent chain."""
        return self._runtime.space.all_bindings()

    def local_bindings(self) -> dict[Symbol, object]:
        """Return local bindings only."""
        return self._runtime.space.local_bindings()

    def hidden_bindings(self) -> dict[Symbol, object]:
        """Return hidden bindings."""
        result: dict[Symbol, object] = {}
        current: SymbolSpace | None = self._runtime.space
        while current is not None:
            result.update(current.hidden_bindings())
            current = current.parent
        return result

    def cache_lookup(self, key: object) -> object:
        """Look up a value in the cache."""
        return self._runtime.space.cache_lookup(key)

    def cache_define(self, key: object, value: object) -> object:
        """Define a value in the cache."""
        return self._runtime.space.cache_define(key, value)

    def cache_discard(self, key: object) -> None:
        """Remove a value from the cache."""
        self._runtime.space.cache_discard(key)

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
        argument_evaluator: ArgumentEvaluator | None = None,
        signature: OperatorSignature | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | Callable[..., object]:
        return self._runtime.register_pure(
            name, func, doc=doc, argument_evaluator=argument_evaluator, signature=signature
        )

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
        # Note: RuntimeSpace expects RuntimeSpace, but we pass Environment for compatibility
        # The operators will receive Environment instances
        return self._runtime.register_scope(name, func, doc=doc, signature=signature)  # type: ignore

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
        return self._runtime.register_control(name, func, doc=doc, signature=signature)  # type: ignore

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
        return self._runtime.register_effect(name, func, doc=doc, signature=signature)  # type: ignore

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
        return self._runtime.register_meta(name, func, doc=doc, signature=signature)  # type: ignore

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
    qy.session.create_standard_runtime_space() instead.

    DEPRECATED: Use qy.session.create_standard_runtime_space() in new code.
    """
    from qy.session.runtime_space import create_standard_runtime_space

    runtime = create_standard_runtime_space(literal_resolver=literal_resolver)

    # Wrap in Environment for backward compatibility
    env = Environment.__new__(Environment)
    env._runtime = runtime
    return env
