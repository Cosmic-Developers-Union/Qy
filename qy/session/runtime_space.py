# coding: utf-8
"""Runtime symbol-space utilities for operator registration.

目标：
- 提供基于 SymbolSpace 的运行时操作符注册功能
- 替代 Environment 的 register_* 方法
- 作为唯一的运行时环境抽象

禁止：
- 不得包含 VM 执行逻辑
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.core.operator_signature import OperatorSignature
    from qy.core.operators import ArgumentEvaluator
    from qy.core.symbol_space import ChainFrame
    from qy.core.symbol_space import SymbolSpace
    from qy.frontend.reader import Symbol
    from qy.session.profile import LiteralResolver
    from qy.session.profile import ProfileConfig

__all__ = [
    "Environment",
    "RuntimeSpace",
    "create_standard_runtime_space",
    "standard_environment",
]


class RuntimeSpace:
    """Runtime symbol-space wrapper with operator registration support.

    This is the primary runtime environment abstraction for QyLang. It wraps
    SymbolSpace + ProfileConfig and provides operator registration, symbol
    resolution with literal fallback, and child-space creation.
    """

    def __init__(
        self,
        bindings_or_space: Mapping[Symbol, object] | SymbolSpace | None = None,
        parent_or_profile: RuntimeSpace | ProfileConfig | None = None,
        literal_resolver: LiteralResolver | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> None:
        from qy.core.symbol_space import SymbolSpace as _SymbolSpace
        from qy.session.profile import ProfileConfig as _ProfileConfig

        if isinstance(bindings_or_space, _SymbolSpace):
            self._space = bindings_or_space
            if isinstance(parent_or_profile, _ProfileConfig):
                self._profile = parent_or_profile
            elif isinstance(parent_or_profile, RuntimeSpace):
                self._profile = parent_or_profile._profile
            else:
                self._profile = _ProfileConfig(literal_resolver)
        elif isinstance(parent_or_profile, RuntimeSpace):
            parent_space = parent_or_profile._space
            self._space = parent_space.child(
                bindings_or_space, name=name, writable=writable, lazy=lazy
            )
            self._profile = parent_or_profile._profile
        else:
            profile = (
                parent_or_profile
                if isinstance(parent_or_profile, _ProfileConfig)
                else _ProfileConfig(literal_resolver)
            )
            if bindings_or_space:
                self._space = _SymbolSpace(
                    bindings_or_space, name=name, writable=writable, lazy=lazy
                )
            else:
                self._space = _SymbolSpace(name=name, writable=writable, lazy=lazy)
            self._profile = profile

    @property
    def space(self) -> SymbolSpace:
        return self._space

    @property
    def profile(self) -> ProfileConfig:
        return self._profile

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

    def resolve(self, symbol: Symbol) -> object:
        """Resolve a symbol along the symbol-space-chain.

        The pre-ssc head already chains lisp-ss / number-ss / char-ss / string-ss
        with ``(membership, resolver)`` pairs, so literal resolution is a real
        chain walk. A custom ``literal_resolver`` (set via the profile) can
        still override; it runs **after** the chain miss as the only escape
        hatch.
        """
        from qy.core.symbol_space import MISSING

        value = self._space.resolve(symbol)
        if value is not MISSING:
            return value
        return self._profile.resolve_literal(symbol)

    def define(self, symbol: Symbol, value: object) -> object:
        return self._space.define(symbol, value)

    def define_once(self, symbol: Symbol, value: object) -> object:
        return self._space.define_once(symbol, value)

    def define_hidden(self, symbol: Symbol, value: object) -> object:
        return self._space.define_hidden(symbol, value)

    def child(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> RuntimeSpace:
        child_space = self._space.child(bindings, name=name, writable=writable, lazy=lazy)
        return RuntimeSpace(child_space, self._profile)

    def fold_from(
        self,
        source: Mapping[Symbol, object],
        names: Iterable[Symbol],
    ) -> None:
        self._space.fold_from(source, names)

    def pre_symbol_space_chain(self) -> tuple[ChainFrame, ...]:
        return self._space.chain().frames()

    def bindings(self) -> dict[Symbol, object]:
        return self._space.all_bindings()

    def local_bindings(self) -> dict[Symbol, object]:
        return self._space.local_bindings()

    def hidden_bindings(self) -> dict[Symbol, object]:
        result: dict[Symbol, object] = {}
        from qy.core.symbol_space import SymbolSpace as _SymbolSpace

        current: _SymbolSpace | None = self._space
        while current is not None:
            result.update(current.hidden_bindings())
            current = current.parent
        return result

    def cache_lookup(self, key: object) -> object:
        return self._space.cache_lookup(key)

    def cache_define(self, key: object, value: object) -> object:
        return self._space.cache_define(key, value)

    def cache_discard(self, key: object) -> None:
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
        from qy.core.operators import PureOperator
        from qy.frontend.reader import Symbol

        def register(func: Callable[..., object]) -> Callable[..., object]:
            self.define(Symbol(name), PureOperator(name, func, doc, argument_evaluator, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_scope(
        self,
        name: str,
        func: Callable[[tuple[object, ...], RuntimeSpace], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], RuntimeSpace], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        from qy.core.operators import ScopeOperator
        from qy.frontend.reader import Symbol

        def register(
            func: Callable[[tuple[object, ...], RuntimeSpace], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), ScopeOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_control(
        self,
        name: str,
        func: Callable[[tuple[object, ...], RuntimeSpace], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], RuntimeSpace], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        from qy.core.operators import ControlOperator
        from qy.frontend.reader import Symbol

        def register(
            func: Callable[[tuple[object, ...], RuntimeSpace], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), ControlOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_effect(
        self,
        name: str,
        func: Callable[[tuple[object, ...], RuntimeSpace], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], RuntimeSpace], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        from qy.core.operators import EffectOperator
        from qy.frontend.reader import Symbol

        def register(
            func: Callable[[tuple[object, ...], RuntimeSpace], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), EffectOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_meta(
        self,
        name: str,
        func: Callable[[tuple[object, ...], RuntimeSpace], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], RuntimeSpace], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        from qy.core.operators import MetaOperator
        from qy.frontend.reader import Symbol

        def register(
            func: Callable[[tuple[object, ...], RuntimeSpace], object],
        ) -> Callable[..., object]:
            self.define(Symbol(name), MetaOperator(name, func, doc, signature))
            return func

        if func is None:
            return register
        return register(func)

    def register_evaluation(
        self,
        name: str,
        func: Callable[[tuple[object, ...], RuntimeSpace], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], RuntimeSpace], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        return self.register_control(name, func, doc=doc, signature=signature)

    def register_syntax(
        self,
        name: str,
        func: Callable[[tuple[object, ...], RuntimeSpace], object] | None = None,
        *,
        doc: str = "",
        signature: OperatorSignature | None = None,
    ) -> (
        Callable[[Callable[[tuple[object, ...], RuntimeSpace], object]], Callable[..., object]]
        | Callable[..., object]
    ):
        return self.register_meta(name, func, doc=doc, signature=signature)


def create_standard_runtime_space(
    *,
    literal_resolver: LiteralResolver | None = None,
) -> RuntimeSpace:
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig(literal_resolver)
    space = profile.create_standard_space()
    return RuntimeSpace(space, profile)


Environment = RuntimeSpace

standard_environment = create_standard_runtime_space
