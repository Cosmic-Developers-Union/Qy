# coding: utf-8
"""Session profile and literal resolution.

目标：
- 提供 profile 配置和 literal resolver
- 管理 pre-symbol-space-chain 的构建
- 提供标准 profile 的初始化

当前：
- 完整实现，使用基于 symbol-space 的字面量解析
- 从 qy/environment.py 迁移相关功能

禁止：
- 不得包含 VM 执行逻辑
- 不得依赖具体的 stdlib 实现
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.core.symbol_space import SymbolSpace
    from qy.reader import Symbol

__all__ = [
    "LiteralResolver",
    "ProfileConfig",
]

LiteralResolver = Callable[["Symbol"], object]


class ProfileConfig:
    """Configuration for a Qy profile.

    A profile defines:
    - How to resolve literal symbols (numbers, strings, etc.)
    - What standard bindings are available
    - The initial symbol-space-chain structure

    The profile now uses pre-symbol-space (pre-ss) for literal resolution,
    replacing the old function-based resolver approach.
    """

    def __init__(
        self,
        literal_resolver: LiteralResolver | None = None,
        *,
        use_pre_ss: bool = True,
    ) -> None:
        self._literal_resolver = literal_resolver
        self._use_pre_ss = use_pre_ss
        self._pre_ss: SymbolSpace | None = None

    @property
    def literal_resolver(self) -> LiteralResolver | None:
        return self._literal_resolver

    def resolve_literal(self, symbol: Symbol) -> object:
        """Resolve a symbol as a literal value.

        This is called when a symbol is not found in any symbol-space.

        If use_pre_ss is True (default), uses the pre-symbol-space architecture.
        Otherwise, falls back to the legacy function-based resolver.
        """
        # If custom resolver is provided, always use it (takes precedence)
        if self._literal_resolver is not None:
            return self._literal_resolver(symbol)

        if self._use_pre_ss:
            return self._resolve_literal_with_pre_ss(symbol)

        from qy.literals import resolve_default_literal

        return resolve_default_literal(symbol)

    def _resolve_literal_with_pre_ss(self, symbol: Symbol) -> object:
        """Resolve a symbol using pre-symbol-space architecture."""
        from qy.session.pre_ss import resolve_literal_in_pre_ss

        if self._pre_ss is None:
            self._pre_ss = self._create_pre_ss()

        from qy.session.pre_ss import _MISSING

        result = resolve_literal_in_pre_ss(symbol, self._pre_ss)
        if result is not _MISSING:
            return result

        from qy.errors import QyResolveError

        raise QyResolveError(
            f"unresolved symbol {symbol.name!r}",
            span=symbol.span,
            metadata={"symbol": symbol.name},
        )

    def _create_pre_ss(self) -> SymbolSpace:
        """Create the pre-symbol-space for literal resolution."""
        from qy.session.pre_ss import create_pre_ssc

        return create_pre_ssc()

    def create_standard_space(self) -> SymbolSpace:
        """Create a standard symbol-space with stdlib bindings.

        This creates the base symbol-space for a standard Qy environment,
        including the pre-symbol-space-chain for literal resolution.
        """
        from qy.core.symbol_space import SymbolSpace
        from qy.std import standard_profile_bindings

        if self._use_pre_ss:
            # Create stdlib layer
            stdlib_bindings = standard_profile_bindings()
            stdlib_layer = SymbolSpace(
                stdlib_bindings,
                name="stdlib",
                writable=False,
            )
            # Create pre-ssc with stdlib
            from qy.session.pre_ss import create_pre_ssc

            return create_pre_ssc(stdlib_layer)

        # Legacy path: no pre-ss integration
        stdlib_layer = SymbolSpace(
            standard_profile_bindings(),
            name="stdlib",
            writable=False,
        )
        return stdlib_layer.child(name="writable-head", writable=True)
