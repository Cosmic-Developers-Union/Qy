# coding: utf-8
"""``from`` 语义的唯一 fold 实现。.

目标：
- 把「选择性 fold 模块导出到当前 symbol-space」收口成一份实现，供运行时算子
  (``qy.import_.operators``) 与 register VM (``qy.vm.instance.machine``) 共用。
- ``from`` 是受 ``exports`` 约束的选择性 fold；宏导出在运行期没有可 fold 的绑定，
  跳过而不是报错；其余缺失导出报错。

禁止：
- 不得执行 module body；求值由 pipeline / VM 承担。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Sequence
from typing import TYPE_CHECKING

from qy.core.syntax import Symbol
from qy.import_.module import StandardModule
from qy.import_.parse import ImportSpec

if TYPE_CHECKING:
    from qy.session.runtime_space import RuntimeSpace as Environment

__all__ = ["fold_import", "iter_selected_exports", "missing_export_names"]


def _never(_module_name: str, _name: Symbol) -> bool:
    return False


def _export_kind(module: StandardModule, name: Symbol) -> str:
    """单一 membership 规则：``runtime`` / ``macro`` / ``missing``。."""
    if name in module.exports:
        return "runtime"
    if name in module.macro_exports:
        return "macro"
    return "missing"


def missing_export_names(specs: Sequence[object], module: StandardModule) -> tuple[Symbol, ...]:
    """返回既不是 runtime 导出、也不是宏导出的 spec 名（供诊断使用）。."""
    return tuple(
        spec.name
        for spec in specs
        if isinstance(spec, ImportSpec) and _export_kind(module, spec.name) == "missing"
    )


def iter_selected_exports(
    module_name: str,
    specs: Sequence[object],
    module: StandardModule,
    *,
    is_compile_time_macro_export: Callable[[str, Symbol], bool] | None = None,
    require: bool = True,
) -> Iterator[tuple[Symbol, object, bool]]:
    """Yield ``(alias, binding, is_macro)`` for a module's selected exports.

    This is the single fold primitive shared by the runtime ``from`` operator,
    the register VM, and the compile-time provisional module builder: all three
    must agree on which specs map to runtime exports, macro exports, exchange
    format macro exports, or are missing.

    ``require=True`` raises ``KeyError`` for a missing export (runtime path);
    ``require=False`` silently skips it (the provisional path is best-effort).
    """
    is_macro = is_compile_time_macro_export or _never
    for spec in specs:
        if not isinstance(spec, ImportSpec):
            continue
        kind = _export_kind(module, spec.name)
        if kind == "runtime":
            yield spec.alias, module.resolve(spec.name), False
        elif kind == "macro":
            yield spec.alias, module.resolve_macro(spec.name), True
        elif is_macro(module_name, spec.name):
            # 交换格式携带的「编译期宏导出」运行期没有绑定。
            continue
        elif require:
            raise KeyError(f"module {module_name!r} has no export {spec.name.name!r}")


def fold_import(
    env: Environment,
    module_name: str,
    specs: Sequence[object],
    module: StandardModule,
    *,
    is_compile_time_macro_export: Callable[[str, Symbol], bool] | None = None,
) -> None:
    """Selectively fold a module's runtime exports into ``env``.

    冲突按目标空间的 define-once 语义处理：``RuntimeSpace.fold_from`` 会先检查所有
    别名再写入，因此冲突导入是原子的（不会留下半导入状态）。
    """
    bindings: dict[Symbol, object] = {}
    for alias, binding, is_macro_export in iter_selected_exports(
        module_name,
        specs,
        module,
        is_compile_time_macro_export=is_compile_time_macro_export,
    ):
        if is_macro_export:
            # 宏导出已在 macro.expand 阶段处理，运行期没有绑定可 fold。
            continue
        bindings[alias] = binding
    if bindings:
        env.fold_from(bindings, list(bindings.keys()))
