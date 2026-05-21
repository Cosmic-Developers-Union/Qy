# coding: utf-8
"""Session profile and literal resolution.

目标：
- 提供 profile 配置和 literal resolver
- 管理 pre-symbol-space-chain 的构建
- 提供标准 profile 的初始化

当前：
- 完整实现，从 qy/environment.py 迁移相关功能

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
    """

    def __init__(
        self,
        literal_resolver: LiteralResolver | None = None,
    ) -> None:
        self._literal_resolver = literal_resolver

    @property
    def literal_resolver(self) -> LiteralResolver | None:
        return self._literal_resolver

    def resolve_literal(self, symbol: Symbol) -> object:
        """Resolve a symbol as a literal value.

        This is called when a symbol is not found in any symbol-space.
        """
        if self._literal_resolver is not None:
            return self._literal_resolver(symbol)
        from qy.literals import resolve_default_literal

        return resolve_default_literal(symbol)

    def create_standard_space(self) -> SymbolSpace:
        """Create a standard symbol-space with stdlib bindings.

        This creates the base symbol-space for a standard Qy environment.
        """
        from qy.core.symbol_space import SymbolSpace
        from qy.std import standard_profile_bindings

        # Create non-writable stdlib layer
        stdlib_layer = SymbolSpace(
            standard_profile_bindings(),
            name="stdlib",
            writable=False,
        )
        # Create writable head for user definitions
        return stdlib_layer.child(name="writable-head", writable=True)
