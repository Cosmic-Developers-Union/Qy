# coding: utf-8
"""Session profile configuration.

目标:
- 提供 profile 配置 (含可选 ``literal_resolver`` 钩子)。
- 提供标准 profile 的初始化, 即把 stdlib bindings 装进 pre-ssc 的特定层。

现状:
- ``ProfileConfig`` 不再内建任何 literal resolution 兜底; 字面量的解析由
  number-ss / char-ss / string-ss 通过 ``(membership, resolver)`` 在 ssc
  walk 中完成。``literal_resolver`` 仅作为用户级 escape hatch (例如测试
  注入特殊解析器)。
- ``create_standard_space`` 单一路径: stdlib → pre-ssc。

禁止:
- 不得包含 VM 执行逻辑。
- 不得依赖具体的 stdlib 实现细节 (只通过 ``standard_profile_bindings``)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qy.core.symbol_space import SymbolSpace
    from qy.frontend.reader import Symbol

__all__ = [
    "LiteralResolver",
    "ProfileConfig",
]

LiteralResolver = Callable[["Symbol"], object]


class ProfileConfig:
    """Configuration for a Qy profile.

    A profile defines:

    - 可选的用户 ``literal_resolver`` 钩子, 在 ssc walk miss 之后被调用
      (作为 escape hatch, 例如测试注入或自定义字面量空间)。
    - 标准 symbol-space-chain 的初始结构 (stdlib 层 + pre-ssc)。

    字面量解析的主路径已经下放到 number-ss / char-ss / string-ss 这些 ss 实例
    自身; ProfileConfig 只在调用方持有的 ss 没接入 pre-ssc 时, 通过一个内建
    pre-ss 副本兜底字面量解析。这一副本是 lazy 创建的, 仅服务于直接构造
    ``RuntimeSpace(bindings_dict, ...)`` 这类绕过 ``create_standard_space``
    的入口。
    """

    def __init__(
        self,
        literal_resolver: LiteralResolver | None = None,
    ) -> None:
        self._literal_resolver = literal_resolver
        self._fallback_pre_ss: SymbolSpace | None = None

    @property
    def literal_resolver(self) -> LiteralResolver | None:
        return self._literal_resolver

    def resolve_literal(self, symbol: Symbol) -> object:
        """Resolve a symbol via the user hook, the fallback pre-ssc, or raise.

        Called by ``RuntimeSpace.resolve`` only **after** the ssc walk on the
        runtime space has missed. Order:

        1. 用户 ``literal_resolver`` 钩子 (如有)。
        2. 内建 pre-ssc 副本 (lazy): 解析数字/字符/字符串字面量与 lisp values。
           为不依赖完整链 (含 stdlib) 的 RuntimeSpace 兜底。
        3. ``QyResolveError``。
        """
        from qy.core.symbol_space import MISSING

        if self._literal_resolver is not None:
            return self._literal_resolver(symbol)

        if self._fallback_pre_ss is None:
            from qy.session.pre_ss import create_pre_ssc

            self._fallback_pre_ss = create_pre_ssc()

        value = self._fallback_pre_ss.resolve(symbol)
        if value is not MISSING:
            return value

        from qy.errors import QyResolveError

        raise QyResolveError(
            f"unresolved symbol {symbol.name!r}",
            span=symbol.span,
            metadata={"symbol": symbol.name},
        )

    def create_standard_space(self) -> SymbolSpace:
        """Create a standard symbol-space with stdlib bindings.

        Layout (parent-first):

        ``lisp-ss → number-ss → char-ss → string-ss → stdlib → pre-ssc-head``

        - ``lisp-ss``: ``T``, ``nil``, ``true``, ``false``, ``none``。
        - ``number-ss`` / ``char-ss`` / ``string-ss``: 字面量识别 + number-ss
          的算子。
        - ``stdlib``: 由 ``qy.std.standard_profile_bindings()`` 提供的 stdlib
          模块合并视图。
        - ``pre-ssc-head``: 用户可写的 head 层。
        """
        from qy.core.symbol_space import SymbolSpace
        from qy.session.pre_ss import create_pre_ssc
        from qy.std import standard_profile_bindings

        stdlib_layer = SymbolSpace(
            standard_profile_bindings(),
            name="stdlib",
            writable=False,
        )
        return create_pre_ssc(stdlib_layer)
