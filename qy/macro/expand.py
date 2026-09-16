# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Macro expansion implementation."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Literal
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Sized


from qy.core.quasiquote import expand_quasiquote
from qy.core.syntax import Form
from qy.core.syntax import Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import cons
from qy.core.syntax import get_span
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil
from qy.diag import Diagnostic
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import read
from qy.import_.parse import parse_from_import
from qy.import_.registry import load_module
from qy.macro import CapturedForm
from qy.macro import MacroDefinition
from qy.macro import MacroExpansionServices
from qy.macro.hygiene import MacroRename
from qy.macro.hygiene import apply_hygiene
from qy.macro.scope import MacroScope
from qy.macro.trace import MacroExpansionTrace
from qy.macro.trace import MacroSourceMapEntry
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.session.runtime_space import create_standard_runtime_space as standard_environment

__all__ = [
    "MacroEffectPolicy",
    "MacroExpansion",
    "MacroExpansionOptions",
    "MacroExpansionTrace",
    "MacroRename",
    "MacroSourceMapEntry",
    "macroexpand",
    "macroexpand_async",
    "macroexpand_source",
    "macroexpand_source_async",
    "module_macro_names",
]

MacroEffectPolicy = Literal["deny", "allow"]
_MAX_MACRO_EXPANSION_DEPTH = 100
_MACRO_NAMESPACE_CACHE_KEY = ("qy", "macro_namespace")
_MODULE_MACRO_NAMESPACE_CACHE_KEY = ("qy", "module_macro_namespace")


# ============================================================================
# Chain form 操作辅助函数
# ============================================================================


def _is_list_form(form: object) -> bool:
    """检查 form 是否为非空 list 形式（非空 chain）。."""
    return is_chain(form) and not is_nil(form)


def _get_operator(form: object) -> object | None:
    """获取 list form 的 operator（第一个元素）。."""
    if is_chain(form) and not is_nil(form):
        return car(form)
    return None


def _get_args(form: object) -> tuple[object, ...]:
    """获取 list form 的参数（除第一个元素外的所有元素）。."""
    if is_chain(form) and not is_nil(form):
        rest = cdr(form)
        if is_nil(rest):
            return ()
        if is_chain(rest):
            return tuple(rest)
        # improper list：tail 本身是最后一个参数
        return (rest,)
    return ()


def _form_length(form: object) -> int:
    """获取 list form 的长度。."""
    if is_chain(form):
        if is_nil(form):
            return 0
        try:
            return len(cast("Sized", form))
        except ValueError:
            # improper list
            count = 0
            current = form
            while is_chain(current):
                count += 1
                current = cdr(current)
            return count + 1
    return 0


def _form_to_list(form: object) -> list[object]:
    """将 list form 转换为 Python list。."""
    if is_chain(form):
        if is_nil(form):
            return []
        try:
            return list(form)
        except ValueError:
            # improper list - 展开所有元素（含 tail）
            result = []
            current = form
            while is_chain(current):
                result.append(car(current))
                current = cdr(current)
            if not is_nil(current):
                result.append(current)
            return result
    return []


def _form_items_and_tail(form: object) -> tuple[list[object], object]:
    """把 chain 拆成「元素列表, tail」；proper list 的 tail 是 nil。."""
    items: list[object] = []
    current = form
    while is_chain(current):
        items.append(car(current))
        current = cdr(current)
    return items, current


def _list_to_form(items: list[object], original: object) -> object:
    """将 Python list 转换回 chain，保留原 form 的 span。."""
    return list_to_chain(items, span=get_span(original))


def _slice_form(form: object, start: int, end: int | None = None) -> list[object]:
    """切片 list form，返回 Python list。."""
    items = _form_to_list(form)
    if end is None:
        return items[start:]
    return items[start:end]


@dataclass(frozen=True, slots=True)
class MacroExpansionOptions:
    max_depth: int = _MAX_MACRO_EXPANSION_DEPTH
    effect_policy: MacroEffectPolicy = "deny"


@dataclass(frozen=True, slots=True)
class MacroExpansion:
    forms: list[Form]
    diagnostics: tuple[Diagnostic, ...] = ()
    traces: tuple[MacroExpansionTrace, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    @property
    def source_map(self) -> tuple[MacroSourceMapEntry, ...]:
        return tuple(trace.source_map_entry() for trace in self.traces)


def macroexpand(
    forms: list[Form],
    env: Environment | None = None,
    *,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    from qy.async_utils import run_coro

    return cast(MacroExpansion, run_coro(macroexpand_async(forms, env, options=options)))


async def macroexpand_async(
    forms: list[Form],
    env: Environment | None = None,
    *,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    runtime_env = env or standard_environment()
    context = MacroExpansionContext.create(runtime_env, options or MacroExpansionOptions())
    expanded_forms: list[Form] = []
    for form in forms:
        try:
            expanded = await _macroexpand_form(
                form,
                context,
                depth=0,
            )
            # 过滤掉编译时构造（macro, from 等返回 nil）
            if not is_nil(expanded):
                expanded_forms.append(cast(Form, expanded))
        except EvaluationError as e:
            context.diagnostics.append(
                Diagnostic(
                    e.message,
                    line=e.line,
                    column=e.column,
                    span=e.span,
                )
            )
    return MacroExpansion(expanded_forms, tuple(context.diagnostics), tuple(context.traces))


def macroexpand_source(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    from qy.async_utils import run_coro

    return cast(
        MacroExpansion,
        run_coro(macroexpand_source_async(source, env, source_name=source_name, options=options)),
    )


async def macroexpand_source_async(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
    options: MacroExpansionOptions | None = None,
) -> MacroExpansion:
    try:
        forms = read(source, source_name=source_name)
    except ReaderSyntaxError as e:
        return MacroExpansion(
            [],
            (Diagnostic(str(e), "error", line=e.line, column=e.column, span=e.span),),
        )
    return await macroexpand_async(forms, env, options=options)


@dataclass(slots=True)
class MacroExpansionContext:
    env: Environment
    options: MacroExpansionOptions
    scope: MacroScope
    macro_namespace: dict[Symbol, MacroDefinition]
    module_macro_namespace: dict[str, dict[Symbol, MacroDefinition]]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    traces: list[MacroExpansionTrace] = field(default_factory=list)
    generated_symbols: list[Symbol] = field(default_factory=list)
    active_expansions: list[Symbol] = field(default_factory=list)
    gensym_counter: int = 0
    hygiene_counter: int = 0

    @classmethod
    def create(
        cls,
        env: Environment,
        options: MacroExpansionOptions,
    ) -> MacroExpansionContext:
        macro_namespace = _macro_namespace(env)
        module_macro_namespace = _module_macro_namespace(env)
        scope = MacroScope(publish_definitions=True, bindings=dict(macro_namespace))
        return cls(env, options, scope, macro_namespace, module_macro_namespace)

    def child_scope(self) -> MacroExpansionContext:
        return MacroExpansionContext(
            self.env,
            self.options,
            self.scope.child(),
            self.macro_namespace,
            self.module_macro_namespace,
            self.diagnostics,
            self.traces,
            self.generated_symbols,
            self.active_expansions,
            self.gensym_counter,
            self.hygiene_counter,
        )

    def child_scope_with_env(self, env: Environment) -> MacroExpansionContext:
        return MacroExpansionContext(
            env,
            self.options,
            self.scope.child(),
            self.macro_namespace,
            self.module_macro_namespace,
            self.diagnostics,
            self.traces,
            self.generated_symbols,
            self.active_expansions,
            self.gensym_counter,
            self.hygiene_counter,
        )

    def sync_from(self, child: MacroExpansionContext) -> None:
        self.gensym_counter = child.gensym_counter
        self.hygiene_counter = child.hygiene_counter

    def define_macro(self, name: Symbol, value: MacroDefinition) -> None:
        self.scope.define(name, value)
        if self.scope.publish_definitions:
            self.macro_namespace[name] = value

    def resolve_macro(self, name: Symbol) -> MacroDefinition | None:
        return self.scope.lookup(name)

    def define_module_macros(
        self,
        module_name: Symbol,
        macros: dict[Symbol, MacroDefinition],
    ) -> None:
        self.module_macro_namespace[module_name.name] = dict(macros)

    def services(self) -> MacroExpansionServices:
        return MacroExpansionServices(self.gensym, self.capture)

    def gensym(self, prefix: object | None = None) -> Symbol:
        self.gensym_counter += 1
        base = _gensym_prefix(prefix)
        symbol = Symbol(f"__qy_gensym_{base}_{self.gensym_counter}")
        self.generated_symbols.append(symbol)
        return symbol

    def capture(self, value: object) -> CapturedForm:
        return CapturedForm(value)

    def fresh_hygienic_symbol(self, prefix: object | None, *, category: str) -> Symbol:
        self.hygiene_counter += 1
        base = _gensym_prefix(prefix)
        return Symbol(f"__qy_hygiene_{category}_{base}_{self.hygiene_counter}")

    def expansion_chain(self) -> tuple[str, ...]:
        return tuple(symbol.name for symbol in self.active_expansions)


async def _macroexpand_form(
    form: object,
    context: MacroExpansionContext,
    *,
    depth: int,
) -> object:
    if depth > context.options.max_depth:
        raise QyArityError(
            f"macro expansion exceeded {context.options.max_depth} nested expansions",
            span=get_span(form),
        )

    # 不是 list form，直接返回
    if not _is_list_form(form):
        return form

    operator = _get_operator(form)
    args = _get_args(form)

    if operator == Symbol("quote"):
        return form
    if operator == Symbol("quasiquote"):
        if len(args) != 1:
            return form
        return await _macroexpand_form(
            expand_quasiquote(args[0], depth=0),
            context,
            depth=depth,
        )
    if operator == Symbol("macro"):
        # Only treat the form as a macro definition when its shape matches
        # ``(macro name (params) body...)``. Otherwise it may be a lambda
        # parameter list such as ``(lambda (macro) ...)`` where the chain
        # ``(macro)`` merely happens to start with the symbol ``macro``.
        definition_items = _form_to_list(form)
        is_definition = (
            len(definition_items) >= 4
            and isinstance(definition_items[1], Symbol)
            and (_is_list_form(definition_items[2]) or is_nil(definition_items[2]))
        )
        if is_definition:
            _define_macro(form, context)
            return nil
    if operator == Symbol("from"):
        _import_macros_from_form(form, context)
        return form
    if operator == Symbol("let"):
        return await _macroexpand_body_form(form, context, depth=depth, body_start=2)
    if operator == Symbol("module"):
        return await _macroexpand_module_form(form, context, depth=depth)
    if operator == Symbol("lambda"):
        return await _macroexpand_body_form(form, context, depth=depth, body_start=2)
    if operator == Symbol("defun"):
        return await _macroexpand_body_form(form, context, depth=depth, body_start=3)
    if operator == Symbol("define"):
        # 特殊处理 (define name (component ...))
        # 这样可以在宏展开阶段注册 component 生成的宏
        items = _form_to_list(form)
        if len(items) == 3:
            name, value = items[1], items[2]
            if isinstance(name, Symbol) and _is_list_form(value):
                value_op = _get_operator(value)
                if value_op == Symbol("component"):
                    from qy.macro.evaluator import evaluate_compile_time_body

                    try:
                        macro_def = await evaluate_compile_time_body((value,), context.env)
                        if isinstance(macro_def, MacroDefinition):
                            context.define_macro(name, macro_def)
                    except Exception:
                        # 如果求值失败，继续正常处理
                        pass
        return await _macroexpand_body_form(form, context, depth=depth, body_start=2)

    if isinstance(operator, Symbol):
        if (value := context.resolve_macro(operator)) is not None:
            context.active_expansions.append(operator)
            try:
                before_symbols = len(context.generated_symbols)
                expanded, renames = await _expand_macro(value, args, context, form)
                generated = tuple(context.generated_symbols[before_symbols:])
                context.traces.append(
                    MacroExpansionTrace(
                        operator,
                        get_span(form),
                        get_span(expanded),
                        depth + 1,
                        form,
                        expanded,
                        generated,
                        renames,
                    )
                )
                return await _macroexpand_form(
                    expanded,
                    context,
                    depth=depth + 1,
                )
            finally:
                context.active_expansions.pop()

    # 递归展开所有子元素
    items = _form_to_list(form)
    expanded_items = [await _macroexpand_form(item, context, depth=depth) for item in items]
    return _list_to_form(expanded_items, form)


async def _macroexpand_body_form(
    form: object,
    context: MacroExpansionContext,
    *,
    depth: int,
    body_start: int,
) -> object:
    form_len = _form_length(form)
    if form_len <= body_start:
        items = _form_to_list(form)
        expanded_items = [await _macroexpand_form(item, context, depth=depth) for item in items]
        return _list_to_form(expanded_items, form)

    prefix_items = _slice_form(form, 0, body_start)
    prefix = [await _macroexpand_form(item, context, depth=depth) for item in prefix_items]

    body_context = context.child_scope()
    body_items = _slice_form(form, body_start)
    body = []
    for item in body_items:
        expanded = await _macroexpand_form(item, body_context, depth=depth)
        # 过滤掉编译时构造（macro 定义返回 nil）
        if not is_nil(expanded):
            body.append(expanded)
    context.sync_from(body_context)
    return _list_to_form([*prefix, *body], form)


async def _macroexpand_module_form(
    form: object,
    context: MacroExpansionContext,
    *,
    depth: int,
) -> object:
    form_len = _form_length(form)
    if form_len <= 2:
        items = _form_to_list(form)
        expanded_items = [await _macroexpand_form(item, context, depth=depth) for item in items]
        return _list_to_form(expanded_items, form)

    prefix_items = _slice_form(form, 0, 2)
    prefix = [await _macroexpand_form(item, context, depth=depth) for item in prefix_items]

    # Build a module-local env pre-populated with compile-time placeholder bindings for
    # defun/defeffect forms in the module body.  This lets macros defined later
    # in the same module body capture those symbols in their definition-site closure.
    module_env = context.env.child()
    body_items = _slice_form(form, 2)
    _prepopulate_module_locals(body_items, module_env)
    body_context = context.child_scope_with_env(module_env)

    body: list[object] = []
    for item in body_items:
        expanded = await _macroexpand_form(item, body_context, depth=depth)
        # 过滤掉编译时构造（macro 定义返回 nil）
        if not is_nil(expanded):
            body.append(expanded)

    context.sync_from(body_context)
    module_name = prefix[1]
    if isinstance(module_name, Symbol):
        exported_macros = _exported_module_macros(body_items, body_context)
        context.define_module_macros(module_name, exported_macros)

        # 缓存 provisional 模块，以便运行时使用
        from qy.project.module import remember_source_module

        remember_source_module(form, context.env)
    return _list_to_form([*prefix, *body], form)


def _prepopulate_module_locals(body: list[object], env: Environment) -> None:
    from qy.sem.runtime import EffectDefinition
    from qy.sem.runtime import UserFunction

    for item in body:
        if not _is_list_form(item):
            continue
        operator = _get_operator(item)
        if operator == Symbol("defun"):
            items = _form_to_list(item)
            if len(items) >= 3 and isinstance(items[1], Symbol):
                name = items[1]
                params_form = items[2] if len(items) > 2 else ()
                # 提取参数列表
                if _is_list_form(params_form) or is_nil(params_form):
                    params_items = _form_to_list(params_form) if _is_list_form(params_form) else []
                    params = tuple(p for p in params_items if isinstance(p, Symbol))
                else:
                    params = ()
                body_forms = tuple(items[3:])
                env.define(name, UserFunction(name, params, body_forms, env))
        elif operator == Symbol("defeffect"):
            items = _form_to_list(item)
            if len(items) >= 2 and isinstance(items[1], Symbol):
                env.define(items[1], EffectDefinition(items[1], resumable=True))


async def _expand_macro(
    macro: MacroDefinition,
    args: tuple[object, ...],
    context: MacroExpansionContext,
    form: object,
) -> tuple[object, tuple[MacroRename, ...]]:
    chain = _format_expansion_chain(context)
    try:
        expanded = await macro.expand(args, context.services())
    except QyEffectSignal as e:
        if context.options.effect_policy == "allow":
            raise
        raise QyRuntimeError(
            f"macro {macro.name.name!r} attempted compile-time effect {e.effect!r}{chain}",
            span=get_span(form),
            cause=e,
            metadata={"macro": macro.name.name, "effect": e.effect},
        ) from e
    except EvaluationError as e:
        raise QyRuntimeError(
            f"macro {macro.name.name!r} failed during compile-time evaluation: {e.message}{chain}",
            span=get_span(form),
            cause=e,
            metadata={
                "macro": macro.name.name,
                "available_compile_time_bindings": tuple(
                    sorted({s.name for s in macro.closure.bindings()} | {"capture", "gensym"})
                ),
            },
        ) from e
    return apply_hygiene(_normalize_macro_result(expanded), macro, args, context)


def _define_macro(form: object, context: MacroExpansionContext) -> None:
    items = _form_to_list(form)
    if len(items) < 4:
        raise QyArityError("macro expects a name, parameter list, and body", span=get_span(form))
    _, name, params, *body = items
    if not isinstance(name, Symbol):
        raise QyTypeError(f"macro name must be a symbol, got {name!r}", span=get_span(name))

    # 处理参数列表
    if not (_is_list_form(params) or is_nil(params)):
        raise QyTypeError(
            f"macro parameters must be a list, got {params!r}",
            span=get_span(params),
        )

    # 解析参数列表，支持 &body 和点对语法
    param_symbols = []
    rest_param = None

    # 检查是否是点对语法 (a b . rest)：improper chain 的 tail 即 rest 参数
    param_items, param_tail = _form_items_and_tail(params) if _is_list_form(params) else ([], nil)
    if not is_nil(param_tail):
        # 点对语法：固定参数在 chain 元素中，rest 参数在 tail 中
        for param in param_items:
            if not isinstance(param, Symbol):
                raise QyTypeError(
                    f"macro parameter must be a symbol, got {param!r}",
                    span=get_span(param),
                )
            param_symbols.append(param)

        if not isinstance(param_tail, Symbol):
            raise QyTypeError(
                f"macro rest parameter must be a symbol, got {param_tail!r}",
                span=get_span(param_tail),
            )
        rest_param = param_tail
    else:
        # 普通列表或 &body 语法
        for i, param in enumerate(param_items):
            if not isinstance(param, Symbol):
                raise QyTypeError(
                    f"macro parameter must be a symbol, got {param!r}",
                    span=get_span(param),
                )

            # 检查是否是 &body 关键字
            if param.name == "&body":
                # &body 后面必须有且只有一个参数
                if i + 1 >= len(param_items):
                    raise QyArityError(
                        "macro &body requires a parameter name",
                        span=get_span(param),
                    )
                if i + 2 < len(param_items):
                    raise QyArityError(
                        "macro &body must be the last parameter",
                        span=get_span(param),
                    )

                rest_param_candidate = param_items[i + 1]
                if not isinstance(rest_param_candidate, Symbol):
                    raise QyTypeError(
                        f"macro rest parameter must be a symbol, got {rest_param_candidate!r}",
                        span=get_span(rest_param_candidate),
                    )
                rest_param = rest_param_candidate
                break

            param_symbols.append(param)

    context.define_macro(
        name,
        MacroDefinition(
            name,
            tuple(param_symbols),
            tuple(body),
            context.env,
            rest_param=rest_param,
        ),
    )


def _gensym_prefix(prefix: object | None) -> str:
    if prefix is None:
        return "sym"
    if isinstance(prefix, Symbol):
        prefix = prefix.name
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(prefix)) or "sym"


def _normalize_macro_result(value: object) -> object:
    if isinstance(value, CapturedForm):
        return CapturedForm(_normalize_macro_result(value.value))
    if is_chain(value):
        # 递归规范化 Chain 的元素
        if is_nil(value):
            return value
        normalized_head = _normalize_macro_result(car(value))
        normalized_tail = _normalize_macro_result(cdr(value))
        return cons(normalized_head, normalized_tail, span=get_span(value))
    return value


def _macro_namespace(env: Environment) -> dict[Symbol, MacroDefinition]:
    try:
        value = env.cache_lookup(_MACRO_NAMESPACE_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_MACRO_NAMESPACE_CACHE_KEY, {})
    return cast(dict[Symbol, MacroDefinition], value)


def _module_macro_namespace(env: Environment) -> dict[str, dict[Symbol, MacroDefinition]]:
    try:
        value = env.cache_lookup(_MODULE_MACRO_NAMESPACE_CACHE_KEY)
    except KeyError:
        value = env.cache_define(_MODULE_MACRO_NAMESPACE_CACHE_KEY, {})
    return cast(dict[str, dict[Symbol, MacroDefinition]], value)


def module_macro_names(env: Environment, module_name: str) -> frozenset[str]:
    """返回某模块在 macro 展开阶段被剥离到 compile-time namespace 的宏名。.

    ``macro.expand`` 会把 ``(module M (macro m ...))`` 中的宏从 module body
    剥离到模块宏命名空间。HIR 只看得到剥离后的 body，因此需要这个只读查询
    来区分"未定义导出"与"宏导出"，避免对合法的宏导出误报。
    """
    macros = _module_macro_namespace(env).get(module_name, {})
    return frozenset(symbol.name for symbol in macros)


def _import_macros_from_form(form: object, context: MacroExpansionContext) -> None:
    try:
        module_name, specs = parse_from_import(form)
    except ValueError as e:
        context.diagnostics.append(
            Diagnostic(str(e), line=_line_of(form), column=_column_of(form), span=get_span(form))
        )
        return

    try:
        macros = _resolve_module_macros(module_name, context)
    except KeyError as e:
        context.diagnostics.append(
            Diagnostic(
                str(e),
                line=_line_of(module_name),
                column=_column_of(module_name),
                span=get_span(module_name),
            )
        )
        return

    for spec in specs:
        macro = macros.get(spec.name)
        if macro is not None:
            context.scope.define(spec.alias, macro)


def _resolve_module_macros(
    module_name: Symbol,
    context: MacroExpansionContext,
) -> dict[Symbol, MacroDefinition]:
    if module_name.name in context.module_macro_namespace:
        return context.module_macro_namespace[module_name.name]
    module = load_module(module_name.name)
    return {
        symbol: value
        for symbol, value in module.macro_exports.items()
        if isinstance(value, MacroDefinition)
    }


def _exported_module_macros(
    body: list[object],
    context: MacroExpansionContext,
) -> dict[Symbol, MacroDefinition]:
    local_bindings = context.scope.bindings or {}
    export_names = _parse_export_names(body)
    if export_names:
        return {
            name: local_bindings[name]
            for name in export_names
            if isinstance(local_bindings.get(name), MacroDefinition)
        }
    return {
        name: value for name, value in local_bindings.items() if isinstance(value, MacroDefinition)
    }


def _parse_export_names(forms: list[object]) -> tuple[Symbol, ...]:
    names: list[Symbol] = []
    for form in forms:
        if _is_special_form(form, "exports"):
            items = _form_to_list(form)
            if len(items) > 1:
                names.extend(_parse_export_items(items[1:]))
    return tuple(names)


def _parse_export_items(items: list[object]) -> list[Symbol]:
    names: list[Symbol] = []
    for item in items:
        if _is_list_form(item):
            names.extend(_parse_export_items(_form_to_list(item)))
        elif isinstance(item, Symbol):
            names.append(item)
    return names


def _is_special_form(form: object, name: str) -> bool:
    return _is_list_form(form) and _get_operator(form) == Symbol(name)


def _line_of(form: object) -> int | None:
    span = get_span(form)
    return None if span is None else span.line


def _column_of(form: object) -> int | None:
    span = get_span(form)
    return None if span is None else span.column


def _format_expansion_chain(context: MacroExpansionContext) -> str:
    chain = context.expansion_chain()
    if len(chain) <= 1:
        return ""
    return f"; expansion chain: {' -> '.join(chain)}"
