# coding: utf-8
"""符号空间折叠和展开。.

目标：
- 提供 fold 和 unfold 操作的统一接口
- 实现符号空间的合成和展开语义
- 支持模块化和命名空间管理

当前：
- 实现基于 ss/ssc 的折叠和展开操作

核心概念：
- 折叠（fold）：将多个 ss 所构成的 ssc 合成为一个 ss 的过程
  对于带有冲突的命名，会引发 effect
- 展开（unfold）：在一个 ss 内部展开一个 ss/ssc 的过程
  类似 Python 的 import，但更强大和灵活

禁止：
- 不得直接实现 module body 求值；求值仍由 pipeline/VM 承担
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qy.import_.loader import ModuleLoader
from qy.import_.loader import get_global_loader
from qy.import_.loader import load_named_space
from qy.import_.loader import set_global_loader
from qy.import_.resolver import FoldSpec
from qy.import_.resolver import UnfoldSpec
from qy.import_.resolver import detect_conflicts
from qy.import_.resolver import resolve_fold
from qy.import_.resolver import resolve_unfold

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping

    from qy.core.symbol_space import SymbolSpace
    from qy.reader import Symbol

__all__ = [
    # Resolver
    "FoldSpec",
    # Loader
    "ModuleLoader",
    "UnfoldSpec",
    "detect_conflicts",
    # Operations
    "fold",
    "get_global_loader",
    "load_named_space",
    "resolve_fold",
    "resolve_unfold",
    "set_global_loader",
    "unfold",
]


def fold(
    target: SymbolSpace,
    source: Mapping[Symbol, object],
    names: Iterable[Symbol],
    aliases: Mapping[Symbol, Symbol] | None = None,
    *,
    check_conflicts: bool = True,
) -> None:
    """折叠操作：将源符号空间的选定绑定合成到目标符号空间。.

    这是 QyLang 的核心操作之一，用于实现模块导入和命名空间合成。

    Args:
        target: 目标符号空间
        source: 源符号空间的绑定
        names: 要折叠的符号名称
        aliases: 可选的别名映射
        check_conflicts: 是否检查命名冲突

    Raises:
        QyRuntimeError: 当存在命名冲突或源中缺少指定符号时

    Example:
        >>> from qy.core.symbol_space import SymbolSpace
        >>> from qy.reader import Symbol
        >>> source = {Symbol("x"): 1, Symbol("y"): 2}
        >>> target = SymbolSpace()
        >>> fold(target, source, [Symbol("x"), Symbol("y")])
        >>> target.lookup(Symbol("x"))
        1
    """
    # 解析折叠规范
    spec = resolve_fold(source, names, aliases)

    # 应用别名
    bindings = spec.apply_aliases()

    # 检查冲突
    if check_conflicts:
        conflicts = detect_conflicts(target.local_bindings(), bindings)
        if conflicts:
            from qy.errors import QyRuntimeError

            conflict_names = ", ".join(s.name for s in conflicts)
            raise QyRuntimeError(
                f"fold operation would create conflicts: {conflict_names}; "
                "use 'let' to shadow or provide aliases"
            )

    # 执行折叠：直接定义绑定（支持别名）
    for name, value in bindings.items():
        if check_conflicts:
            target.define_once(name, value)
        else:
            target.define(name, value)


def unfold(
    target: SymbolSpace,
    source: Mapping[Symbol, object],
    names: Iterable[Symbol] | None = None,
    prefix: str = "",
    *,
    check_conflicts: bool = True,
) -> None:
    """展开操作：在目标符号空间内部展开源符号空间。.

    这是 QyLang 的核心操作之一，类似 Python 的 import，但更强大。
    展开操作会将源符号空间的绑定引入到目标空间，可以选择性地添加前缀。

    Args:
        target: 目标符号空间
        source: 源符号空间的绑定
        names: 要展开的符号名称（None 表示全部）
        prefix: 展开后的符号前缀
        check_conflicts: 是否检查命名冲突

    Raises:
        QyRuntimeError: 当存在命名冲突或源中缺少指定符号时

    Example:
        >>> from qy.core.symbol_space import SymbolSpace
        >>> from qy.reader import Symbol
        >>> source = {Symbol("x"): 1, Symbol("y"): 2}
        >>> target = SymbolSpace()
        >>> unfold(target, source, prefix="mod.")
        >>> target.lookup(Symbol("mod.x"))
        1
    """
    # 解析展开规范
    spec = resolve_unfold(source, names, prefix)

    # 应用前缀
    bindings = spec.apply_prefix()

    # 检查冲突
    if check_conflicts:
        conflicts = detect_conflicts(target.local_bindings(), bindings)
        if conflicts:
            from qy.errors import QyRuntimeError

            conflict_names = ", ".join(s.name for s in conflicts)
            raise QyRuntimeError(
                f"unfold operation would create conflicts: {conflict_names}; "
                "use a different prefix or 'let' to shadow"
            )

    # 执行展开
    for name, value in bindings.items():
        target.define_once(name, value)
