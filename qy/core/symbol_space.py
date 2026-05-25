# coding: utf-8
"""Core symbol-space implementation.

目标：
- 实现 symbol-space 和 symbol-space-chain 的核心语义
- 提供 binding slot 管理和 lookup 机制
- 支持 define-once 语义和 shadow 规则
- 提供 fold 操作用于模块导入

当前：
- 完整实现 symbol-space 和 symbol-space-chain 的核心语义

禁止：
- 不得包含 profile 便利算子
- 不得依赖 VM 执行路径
- 不得混入 literal resolver（属于 session/profile）
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass

from qy.frontend.reader import Symbol

__all__ = [
    "BindingSlot",
    "ChainFrame",
    "SymbolSpace",
    "SymbolSpaceChain",
]


@dataclass(frozen=True, slots=True)
class BindingSlot:
    """A binding slot in a symbol-space.

    Represents a stable address for a symbol binding. The slot can be in one of
    three states:
    - declared but incomplete (pending)
    - completed with a value
    - hidden (internal binding not visible in normal lookup)
    """

    symbol: Symbol
    value: object | None = None
    completed: bool = False
    hidden: bool = False

    def complete(self, value: object) -> BindingSlot:
        """Return a new slot with the value completed."""
        if self.completed:
            from qy.errors import QyRuntimeError

            raise QyRuntimeError(f"binding slot for {self.symbol.name!r} is already completed")
        return BindingSlot(symbol=self.symbol, value=value, completed=True, hidden=self.hidden)


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
    """A symbol-space: a mapping from symbols to binding slots.

    Symbol-space is the core scoping mechanism in Qy. It provides:
    - Once-complete binding semantics (no re-binding in the same space)
    - Shadow support (child spaces can shadow parent bindings)
    - Fold operation (absorb bindings from external sources)
    - Hidden bindings (internal bindings not visible in normal lookup)

    Important: SymbolSpace does NOT handle literal resolution. That belongs to
    the session/profile layer.
    """

    def __init__(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        parent: SymbolSpace | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> None:
        self._bindings: dict[Symbol, object] = dict(bindings or {})
        self._parent = parent
        self._hidden: dict[Symbol, object] = {}
        self._name = name
        self._writable = writable
        self._lazy = lazy
        self._cache: dict[object, object] = parent._cache if parent is not None else {}

    def lookup(self, symbol: Symbol) -> object | None:
        """Look up a symbol in this space and its parent chain.

        Returns the bound value if found, None if not found. Does not perform
        literal resolution - that's the responsibility of the caller.
        """
        if symbol in self._bindings:
            return self._bindings[symbol]
        if symbol in self._hidden:
            return self._hidden[symbol]
        if self._parent is not None:
            return self._parent.lookup(symbol)
        return None

    def has_local_binding(self, symbol: Symbol) -> bool:
        """Check if this space has a local binding for the symbol."""
        return symbol in self._bindings or symbol in self._hidden

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

    def child(
        self,
        bindings: Mapping[Symbol, object] | None = None,
        *,
        name: str = "",
        writable: bool = True,
        lazy: bool = False,
    ) -> SymbolSpace:
        """Create a child symbol-space with this space as parent."""
        return SymbolSpace(bindings, self, name=name, writable=writable, lazy=lazy)

    def chain(self) -> SymbolSpaceChain:
        """Return the symbol-space-chain for this space."""
        return SymbolSpaceChain(self)

    def local_bindings(self) -> dict[Symbol, object]:
        """Return a copy of local bindings (excluding hidden)."""
        return dict(self._bindings)

    def hidden_bindings(self) -> dict[Symbol, object]:
        """Return a copy of hidden bindings."""
        return dict(self._hidden)

    def all_bindings(self) -> dict[Symbol, object]:
        """Return all bindings including parent chain."""
        if self._parent is None:
            return dict(self._bindings)
        result = self._parent.all_bindings()
        result.update(self._bindings)
        return result

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
    from the head (innermost space) to the tail (outermost space).
    """

    def __init__(self, head: SymbolSpace) -> None:
        self._head = head

    def lookup(self, symbol: Symbol) -> object | None:
        """Look up a symbol in the chain."""
        return self._head.lookup(symbol)

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
