# coding: utf-8
"""Core symbol-space implementation.

目标：
- SymbolSpace 提供两个原语：``contains`` (检测) 和 ``lookup`` (查找本层)。
  ``resolve`` 在 ``lookup`` 基础上沿父链回退。
- 单一 ``SymbolSpace`` 类同时表达静态有限空间与无限空间：
  - 有限空间：仅 fixed bindings dict。
  - 无限空间：通过 (membership, resolver) 一对函数动态识别符号 (如 number-ss
    可识别所有数字字面量)。两种形态可共存于同一空间——number-ss 既绑定
    ``+`` / ``-`` 等算子, 也通过 (membership, resolver) 识别 ``42``。
- ``MISSING`` sentinel 严格表达"该 symbol 不存在"; 与"显式绑定到 None" 区分。
- 提供 once-complete binding 与 hygiene 用 hidden binding。
- 提供 fold 操作用于模块导入。

禁止：
- 不得包含 profile 便利算子。
- 不得依赖 VM 执行路径。
- 不得混入 literal resolver 注册策略 (属于 session/profile)。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from qy.frontend.reader import Symbol

__all__ = [
    "MISSING",
    "ChainFrame",
    "MembershipPredicate",
    "SymbolSpace",
    "SymbolSpaceChain",
    "ValueResolver",
]


class _Missing:
    """Sentinel type for "binding does not exist".

    Distinct from ``None``: a symbol may be bound to ``None`` legitimately
    (e.g. Python ``None`` injected as a host value). ``MISSING`` is the
    *absence* of a binding.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Final[_Missing] = _Missing()

MembershipPredicate = Callable[[Symbol], bool]
ValueResolver = Callable[[Symbol], object]


@dataclass(frozen=True, slots=True)
class ChainFrame:
    """One node in the symbol-space-chain.

    Each frame represents a single layer in the chain, with metadata describing
    its role (name), mutability (writable), and loading strategy (lazy). The
    *bindings* dict is a **read-only snapshot** of that layer's local bindings
    at the time the frame was materialized.
    """

    name: str
    bindings: dict[Symbol, object]
    writable: bool
    lazy: bool


class SymbolSpace:
    """A symbol-space: a mapping from symbols to values.

    Symbol-space provides two primitives:

    - ``contains(symbol) -> bool``: 检测 symbol 是否在本层 (有限部分 + 无限部分)。
    - ``lookup(symbol) -> object | MISSING``: 在本层取出 symbol 的绑定值。

    ``resolve(symbol)`` 在 ``lookup`` 基础上沿父链回退,实现 symbol-space-chain
    语义。本层 miss 时递归 parent。

    A space may be:

    - **静态有限**: 仅 fixed bindings dict。
    - **无限**: 通过 ``(membership, resolver)`` 一对函数动态识别符号。
      ``membership(symbol) -> bool`` 决定 symbol 是否属于本空间;
      ``resolver(symbol) -> object | MISSING`` 给出对应值。
    - **同时持有**: number-ss 既绑定 ``+`` / ``-`` 等算子, 也通过
      (membership, resolver) 识别所有数字字面量。

    必须成对提供 ``(membership, resolver)`` 或都不提供; 单独传一个抛
    ``ValueError``。

    Important: SymbolSpace does NOT handle literal resolution policy itself.
    Profile/session decides how to compose pre-defined spaces into the chain.
    """

    def __init__(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        parent: SymbolSpace | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
        membership: MembershipPredicate | None = None,
        resolver: ValueResolver | None = None,
    ) -> None:
        if (membership is None) != (resolver is None):
            raise ValueError("SymbolSpace: 'membership' and 'resolver' must be provided together")
        self._bindings: dict[Symbol, object] = dict(bindings or {})
        self._parent = parent
        self._hidden: dict[Symbol, object] = {}
        self._name = name
        self._writable = writable
        self._lazy = lazy
        self._membership = membership
        self._resolver = resolver
        self._cache: dict[object, object] = parent._cache if parent is not None else {}

    # -- 双原语：本层检测与本层查找 ----------------------------------------

    def contains(self, symbol: Symbol) -> bool:
        """检测 symbol 是否在本层 (有限 bindings/hidden 或动态 membership).

        仅看本层；不走父链。
        """
        if symbol in self._bindings or symbol in self._hidden:
            return True
        if self._membership is not None and self._membership(symbol):
            return True
        return False

    def lookup(self, symbol: Symbol) -> object:
        """在本层取出 symbol 的绑定值; miss 返回 ``MISSING``.

        仅看本层；不走父链。先查 fixed bindings/hidden, 否则若 ``resolver``
        命中则返回该值, 否则 ``MISSING``。
        """
        if symbol in self._bindings:
            return self._bindings[symbol]
        if symbol in self._hidden:
            return self._hidden[symbol]
        if self._resolver is not None:
            value = self._resolver(symbol)
            if value is not MISSING:
                return value
        return MISSING

    def resolve(self, symbol: Symbol) -> object:
        """沿 symbol-space-chain 查找 symbol; 全链 miss 返回 ``MISSING``.

        本层 ``lookup`` 命中则直接返回; 否则递归 parent。
        """
        value = self.lookup(symbol)
        if value is not MISSING:
            return value
        if self._parent is not None:
            return self._parent.resolve(symbol)
        return MISSING

    # -- 兼容旧 API：has_local_binding -------------------------------------

    def has_local_binding(self, symbol: Symbol) -> bool:
        """Check if this space has a local binding (fixed only, excludes membership)."""
        return symbol in self._bindings or symbol in self._hidden

    # -- binding 写入 ------------------------------------------------------

    def define(self, symbol: Symbol, value: object) -> object:
        """Define a symbol in this space.

        This is the basic define operation that allows re-binding. Use
        define_once for strict once-complete semantics.
        """
        self._bindings[symbol] = value
        return value

    def define_once(self, symbol: Symbol, value: object) -> object:
        """Define a symbol with once-complete semantics.

        Raises QyRuntimeError if the symbol is already bound in this space.
        """
        if symbol in self._bindings:
            from qy.errors import QyRuntimeError

            raise QyRuntimeError(
                f"symbol {symbol.name!r} is already bound in this scope; use 'let' to shadow"
            )
        self._bindings[symbol] = value
        return value

    def define_hidden(self, symbol: Symbol, value: object) -> object:
        """Define a hidden binding not visible in normal lookup."""
        self._hidden[symbol] = value
        return value

    def fold_from(
        self,
        source: Mapping[Symbol, object],
        names: Iterable[Symbol],
    ) -> None:
        """Fold selected bindings from source into this space.

        This is the formal fold operation: it absorbs visible bindings from an
        external source (e.g., a module's export view) into the local
        symbol-space, making them local members. define_once semantics apply.
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

    # -- 链构造 ------------------------------------------------------------

    def child(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
        membership: MembershipPredicate | None = None,
        resolver: ValueResolver | None = None,
    ) -> SymbolSpace:
        """Create a child symbol-space with this space as parent."""
        return SymbolSpace(
            bindings,
            self,
            name=name,
            writable=writable,
            lazy=lazy,
            membership=membership,
            resolver=resolver,
        )

    def chain(self) -> SymbolSpaceChain:
        """Return the symbol-space-chain rooted at this space."""
        return SymbolSpaceChain(self)

    # -- 反射 --------------------------------------------------------------

    def local_bindings(self) -> dict[Symbol, object]:
        """Return a copy of local bindings (excluding hidden, excluding dynamic)."""
        return dict(self._bindings)

    def hidden_bindings(self) -> dict[Symbol, object]:
        """Return a copy of hidden bindings."""
        return dict(self._hidden)

    def all_bindings(self) -> dict[Symbol, object]:
        """Return all fixed bindings including parent chain (excludes dynamic)."""
        if self._parent is None:
            return dict(self._bindings)
        result = self._parent.all_bindings()
        result.update(self._bindings)
        return result

    # -- 共享 KV cache (与 binding lookup 解耦) -----------------------------

    def cache_lookup(self, key: object) -> object:
        """Look up a value in the shared cache."""
        return self._cache[key]

    def cache_define(self, key: object, value: object) -> object:
        """Define a value in the shared cache."""
        self._cache[key] = value
        return value

    def cache_discard(self, key: object) -> None:
        """Remove a value from the shared cache."""
        self._cache.pop(key, None)

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
    def parent(self) -> SymbolSpace | None:
        return self._parent


class SymbolSpaceChain:
    """A symbol-space-chain: an ordered sequence of symbol-spaces.

    The chain represents the lookup path for symbol resolution. Lookup proceeds
    from the head (innermost space) outwards.
    """

    def __init__(self, head: SymbolSpace) -> None:
        self._head = head

    def resolve(self, symbol: Symbol) -> object:
        """Look up a symbol along the chain; returns ``MISSING`` if absent."""
        return self._head.resolve(symbol)

    def lookup(self, symbol: Symbol) -> object:
        """Alias of ``resolve`` for chain-level lookup.

        Note: chain-level ``lookup`` is the *chained* operation. Use
        ``SymbolSpace.lookup`` for single-layer lookup.
        """
        return self.resolve(symbol)

    def frames(self) -> tuple[ChainFrame, ...]:
        """Return the chain as a tuple of frames (parent-first order)."""
        frames: list[ChainFrame] = []
        current: SymbolSpace | None = self._head
        while current is not None:
            frame = ChainFrame(
                name=current.name or "<anonymous>",
                bindings=dict(current._bindings),
                writable=current.writable,
                lazy=current.lazy,
            )
            frames.append(frame)
            current = current.parent
        return tuple(reversed(frames))

    @property
    def head(self) -> SymbolSpace:
        return self._head
