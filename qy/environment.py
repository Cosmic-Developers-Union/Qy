# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/core symbol-space + qy/session profile facts

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

__all__ = ["ChainFrame", "Environment", "standard_environment"]

LiteralResolver = Callable[[Symbol], object]


@dataclass(frozen=True, slots=True)
class ChainFrame:
    """One node in the pre-symbol-space-chain.

    Each frame represents a single layer in the environment chain, with
    metadata describing its role (name), mutability (writable), and loading
    strategy (lazy).  The *bindings* dict is a **read-only snapshot** of that
    layer's local bindings at the time the frame was materialised.
    """

    name: str  # e.g. "writable-head", "core-profile", "stdlib"
    bindings: dict[Symbol, object]  # read-only snapshot of local bindings
    writable: bool  # whether ``define`` works here
    lazy: bool  # whether this layer is lazily loaded


class Environment:
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
        self._bindings = dict(bindings or {})
        self._parent = parent
        self._cache: dict[object, object] = parent._cache if parent is not None else {}
        self._hidden: dict[Symbol, object] = {}
        if parent is not None:
            self._literal_resolver = parent._literal_resolver
        else:
            self._literal_resolver: LiteralResolver = literal_resolver or resolve_default_literal
        self._name = name
        self._writable = writable
        self._lazy = lazy

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

    def child(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> Environment:
        return Environment(bindings, self, name=name, writable=writable, lazy=lazy)

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

    def pre_symbol_space_chain(self) -> tuple[ChainFrame, ...]:
        """Return the pre-symbol-space-chain as a tuple of *ChainFrame* nodes.

        The order is parent-first (root at index 0, self at the end), which
        matches the lookup direction: a resolver walks from the innermost
        frame outward.
        """
        frame = ChainFrame(
            name=self._name or "<anonymous>",
            bindings=dict(self._bindings),
            writable=self._writable,
            lazy=self._lazy,
        )
        if self._parent is None:
            return (frame,)
        return (*self._parent.pre_symbol_space_chain(), frame)

    @property
    def name(self) -> str:
        return self._name

    @property
    def writable(self) -> bool:
        return self._writable

    @property
    def lazy(self) -> bool:
        return self._lazy

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

    # The chain is built bottom-up:
    #   root (stdlib layer) <- writable-head (user definitions)
    # The stdlib layer is non-writable so that accidental top-level
    # ``define`` goes into the writable head above it.
    stdlib_layer = Environment(
        standard_profile_bindings(),
        literal_resolver=literal_resolver,
        name="stdlib",
        writable=False,
    )
    return stdlib_layer.child(name="writable-head", writable=True)
