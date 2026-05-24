# coding: utf-8
"""Runtime symbol-space utilities for operator registration.

目标：
- 提供基于 SymbolSpace 的运行时操作符注册功能
- 替代 Environment 的 register_* 方法
- 为迁移提供适配层

当前：
- 新增模块，用于 Environment 迁移

禁止：
- 不得依赖 Environment 类
- 不得包含 VM 执行逻辑
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.core.operator_signature import OperatorSignature
    from qy.core.operators import ArgumentEvaluator
    from qy.core.symbol_space import SymbolSpace
    from qy.frontend.reader import Symbol
    from qy.session.profile import LiteralResolver
    from qy.session.profile import ProfileConfig

__all__ = [
    "RuntimeSpace",
    "create_standard_runtime_space",
]


class RuntimeSpace:
    """Runtime symbol-space wrapper with operator registration support.

    This class provides a thin wrapper around SymbolSpace + ProfileConfig
    to support operator registration patterns used throughout the codebase.
    It serves as a migration path from Environment to the new architecture.
    """

    def __init__(
        self,
        space: SymbolSpace,
        profile: ProfileConfig,
    ) -> None:
        self._space = space
        self._profile = profile

    @property
    def space(self) -> SymbolSpace:
        """Access the underlying symbol-space."""
        return self._space

    @property
    def profile(self) -> ProfileConfig:
        """Access the profile configuration."""
        return self._profile

    def resolve(self, symbol: Symbol) -> object:
        """Resolve a symbol to its value."""
        result = self._space.lookup(symbol)
        if result is not None:
            return result
        return self._profile.resolve_literal(symbol)

    def define(self, symbol: Symbol, value: object) -> object:
        """Define a symbol in this space."""
        return self._space.define(symbol, value)

    def define_once(self, symbol: Symbol, value: object) -> object:
        """Define a symbol with once-complete semantics."""
        return self._space.define_once(symbol, value)

    def define_hidden(self, symbol: Symbol, value: object) -> object:
        """Define a hidden binding."""
        return self._space.define_hidden(symbol, value)

    def child(
        self,
        bindings: dict[Symbol, object] | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> RuntimeSpace:
        """Create a child runtime space."""
        child_space = self._space.child(bindings, name=name, writable=writable, lazy=lazy)
        return RuntimeSpace(child_space, self._profile)

    def register_pure(
        self,
        name: str,
        func: Callable[..., object] | None = None,
        *,
        doc: str = "",
        argument_evaluator: ArgumentEvaluator | None = None,
        signature: OperatorSignature | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | Callable[..., object]:
        """Register a pure operator."""
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
        """Register a scope operator."""
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
        """Register a control operator."""
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
        """Register an effect operator."""
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
        """Register a meta operator."""
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
        """Register an evaluation operator (alias for control)."""
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
        """Register a syntax operator (alias for meta)."""
        return self.register_meta(name, func, doc=doc, signature=signature)


def create_standard_runtime_space(
    *,
    literal_resolver: LiteralResolver | None = None,
) -> RuntimeSpace:
    """Create a standard runtime space with stdlib bindings.

    This is the new entry point that replaces standard_environment().
    """
    from qy.session.profile import ProfileConfig

    profile = ProfileConfig(literal_resolver)
    space = profile.create_standard_space()
    return RuntimeSpace(space, profile)
