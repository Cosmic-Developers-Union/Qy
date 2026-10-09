# coding: utf-8
"""hir.lower — Form → HIR lowering 实现。.

LowerHIRPass 在 ``qy/passes/hir/lower_pass.py`` 中通过调用 ``lower`` 把
macro-expanded core forms 降为 ``ProgramIR``。这里只放算法实现；任何外部
""完整源到字节码"调用必须通过 ``qy.build.pipeline`` 提供的 pipeline 入口。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.core import TypeName
from qy.core.operator_signature import OperatorSignature
from qy.core.operator_signature import format_arity_message
from qy.core.operator_signature import lookup_operator_signature
from qy.core.operators import value_uses_eager_arguments
from qy.core.quasiquote import expand_quasiquote
from qy.core.syntax import Form
from qy.core.syntax import Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import get_span
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import nil
from qy.diag import Diagnostic
from qy.errors import EvaluationError
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import read
from qy.import_.from_fold import iter_selected_exports
from qy.import_.from_fold import missing_export_names
from qy.import_.loader import resolve_known_module
from qy.import_.parse import parse_from_import
from qy.ir import AllExpr
from qy.ir import ApplyExpr
from qy.ir import AssertExpr
from qy.ir import Binding
from qy.ir import CacheExpr
from qy.ir import CallExpr
from qy.ir import CondClause
from qy.ir import CondExpr
from qy.ir import DefeffectExpr
from qy.ir import DefineExpr
from qy.ir import EffectHandler
from qy.ir import FromImportExpr
from qy.ir import HandleExpr
from qy.ir import IRExpr
from qy.ir import LambdaExpr
from qy.ir import LetBinding
from qy.ir import LetExpr
from qy.ir import LiteralExpr
from qy.ir import MacroExpr
from qy.ir import ModuleExpr
from qy.ir import ParallelExpr
from qy.ir import PerformExpr
from qy.ir import PipelineExpr
from qy.ir import ProgramIR
from qy.ir import QuoteExpr
from qy.ir import RaceExpr
from qy.ir import ResumeExpr
from qy.ir import RuntimeEvalExpr
from qy.ir import SymbolRefExpr
from qy.ir import SymbolSpace
from qy.ir import UnresolvedSymbolExpr
from qy.macro import CapturedForm
from qy.macro.expand import module_macro_names
from qy.project.module import remember_source_module
from qy.sem.classify import literal_type
from qy.sem.classify import operator_kind_for_value
from qy.sem.classify import value_type
from qy.session.pre_ss import default_literal_type
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.session.runtime_space import create_standard_runtime_space as standard_environment

__all__ = [
    "LoweringContext",
    "Scope",
    "lower",
    "lower_source",
]


@dataclass(frozen=True, slots=True)
class Scope:
    """Scope tracks bindings during HIR lowering.

    This is a transitional BindingRef facade over explicit symbol-space-chain
    facts.  Root scopes are initialized from ``RuntimeSpace.pre_symbol_space_chain()``
    snapshots instead of flattening live runtime env bindings.
    """

    bindings: dict[Symbol, Binding] | None = None
    parent: Scope | None = None
    symbol_space: SymbolSpace | None = None

    def child(self, name: str = "anonymous") -> Scope:
        """Create a child scope with its own symbol space."""
        parent_space = self.symbol_space
        child_space = parent_space.child(name) if parent_space else SymbolSpace(name)
        return Scope(parent=self, symbol_space=child_space)

    def define(self, binding: Binding) -> Scope:
        bindings = dict(self.bindings or {})
        bindings[binding.symbol] = binding
        return Scope(bindings, self.parent, self.symbol_space)

    def has_local(self, symbol: Symbol) -> bool:
        return self.bindings is not None and symbol in self.bindings

    def lookup(self, symbol: Symbol) -> Binding | None:
        if self.bindings is not None and symbol in self.bindings:
            return self.bindings[symbol]
        if self.parent is not None:
            return self.parent.lookup(symbol)
        return None


@dataclass(slots=True)
class LoweringContext:
    env: Environment
    diagnostics: list[Diagnostic]
    next_binding_id: int = 0

    @classmethod
    def create(cls, env: Environment | None = None) -> LoweringContext:
        return cls(env or standard_environment(), [], 0)

    def diagnostic(self, message: str, form: object | None = None) -> None:
        span = get_span(form) if form is not None else None
        self.diagnostics.append(
            Diagnostic(
                message,
                line=None if span is None else span.line,
                column=None if span is None else span.column,
                span=span,
            )
        )

    def allocate_binding_id(self) -> int:
        """Allocate a unique binding ID for BindingRef."""
        binding_id = self.next_binding_id
        self.next_binding_id += 1
        return binding_id


def lower_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> ProgramIR:
    try:
        forms = read(source, source_name=source_name)
    except ReaderSyntaxError as e:
        return ProgramIR(
            (),
            (Diagnostic(str(e), "error", line=e.line, column=e.column, span=e.span),),
        )
    return lower(forms, env)


def lower(forms: list[Form], env: Environment | None = None) -> ProgramIR:
    context = LoweringContext.create(env)
    # Initialize root symbol space named "Main" as per ir-design.md
    root_space = SymbolSpace(name="Main")
    scope = _scope_from_environment(context.env, root_space)
    scope = _predeclare_callable_definitions(tuple(forms), scope, context)
    body: list[IRExpr] = []
    for form in forms:
        # Top-level forms are not in tail position; tail propagation starts from
        # function / lambda / cond / pipeline bodies (see hir-spec.md §3.4 H5).
        expr = _lower_form(form, scope, context, tail=False)
        body.append(expr)
        scope = _scope_after_form(form, expr, scope, context)
    return ProgramIR(tuple(body), tuple(context.diagnostics), root_space=root_space)


def _scope_from_environment(env: Environment, symbol_space: SymbolSpace) -> Scope:
    parent_scope: Scope | None = None
    parent_space: SymbolSpace | None = None
    for frame in env.pre_symbol_space_chain():
        frame_space = SymbolSpace(name=frame.name, parent=parent_space)
        frame_scope = Scope(parent=parent_scope, symbol_space=frame_space)
        for symbol, value in frame.bindings.items():
            frame_scope = frame_scope.define(
                Binding(
                    symbol,
                    "builtin",
                    value_type(value),
                    frame_space,
                    operator_kind=operator_kind_for_value(value),
                    eager_arguments=value_uses_eager_arguments(value),
                    value=value,
                )
            )
        parent_scope = frame_scope
        parent_space = frame_space
    return Scope(parent=parent_scope, symbol_space=symbol_space)


def _lower_form(
    form: object,
    scope: Scope,
    context: LoweringContext,
    *,
    tail: bool = False,
    symbol_as_data: bool = False,
) -> IRExpr:
    # Handle CapturedForm - unwrap and lower the captured value
    if isinstance(form, CapturedForm):
        return _lower_form(form.value, scope, context, tail=tail, symbol_as_data=symbol_as_data)

    if isinstance(form, Symbol):
        return _lower_symbol(form, scope, context, symbol_as_data=symbol_as_data)
    if is_chain(form):
        operator = car(form)
        args = _proper_chain_items(cdr(form))
        if args is None:
            context.diagnostic("dotted form cannot be evaluated as a call", form)
            return LiteralExpr(form, "unknown", get_span(form))

        if isinstance(operator, Symbol):
            match operator.name:
                case "quote":
                    return _lower_quote(tuple(args), context, form)
                case "quasiquote":
                    return _lower_quasiquote(tuple(args), scope, context, form, tail=tail)
                case "eval":
                    return _lower_eval(tuple(args), scope, context, form)
                case "macro":
                    return _lower_macro(form, scope, context)
                case "cond":
                    return _lower_cond(tuple(args), scope, context, form, tail=tail)
                case "let":
                    return _lower_let(tuple(args), scope, context, form, tail=tail)
                case "lambda":
                    return _lower_lambda(tuple(args), scope, context, form)
                case "component":
                    return _lower_component(tuple(args), scope, context, form)
                case "defun":
                    return _lower_defun(form, scope, context)
                case "defeffect":
                    return _lower_defeffect(form, scope, context)
                case "module":
                    return _lower_module(form, scope, context)
                case "from":
                    return _lower_from(form, context)
                case "perform":
                    return _lower_perform(tuple(args), scope, context, form)
                case "handle":
                    return _lower_handle(tuple(args), scope, context, form, tail=tail)
                case "resume":
                    return _lower_resume(tuple(args), scope, context, form)
                case "assert":
                    return _lower_assert(tuple(args), scope, context, form)
                case "define":
                    return _lower_define(form, scope, context)
                case "pipeline":
                    return _lower_pipeline(tuple(args), scope, context, form, tail=tail)
                case "parallel":
                    return _lower_parallel(tuple(args), scope, context, form)
                case "all":
                    return _lower_all(tuple(args), scope, context, form)
                case "race":
                    return _lower_race(tuple(args), scope, context, form)
                case "apply":
                    return _lower_apply(tuple(args), scope, context, form)
                case "cache":
                    return _lower_cache(tuple(args), scope, context, form)

        operator_expr = _lower_form(operator, scope, context)
        if (
            isinstance(operator_expr, SymbolRefExpr)
            and operator_expr.binding.operator_kind == "meta"
        ):
            context.diagnostic(
                f"meta operator {operator_expr.symbol.name!r} can only run during macro expansion",
                form,
            )
            return UnresolvedSymbolExpr(operator_expr.symbol, get_span(form))

        args_as_data = _call_uses_non_eager_arguments(operator_expr)
        lowered_args = tuple(
            _lower_form(
                arg,
                scope,
                context,
                symbol_as_data=args_as_data and not _argument_is_eager(operator_expr, idx),
            )
            for idx, arg in enumerate(args)
        )
        return CallExpr(
            operator_expr,
            lowered_args,
            get_span(form),
            _infer_call_type(operator, tuple(lowered_args), operator_expr, context, form),
            tail,
        )

    return LiteralExpr(_canonicalize_host_value(form), literal_type(form), get_span(form))


def _proper_chain_items(chain: object) -> list[object] | None:
    """把 proper chain 拆成元素列表；非 chain 或 improper chain 返回 None。."""
    if is_nil(chain):
        return []
    if not is_chain(chain):
        return None
    items: list[object] = []
    current: object = chain
    while is_chain(current):
        items.append(car(current))
        current = cdr(current)
    return items if is_nil(current) else None


def _form_to_list(form: object) -> list[object]:
    """将 form（Chain）转换为 list；improper chain 返回元素列表。."""
    if is_chain(form):
        items, tail = _chain_items_and_tail(form)
        if not is_nil(tail):
            items.append(tail)
        return items
    return []


def _chain_items_and_tail(chain: object) -> tuple[list[object], object]:
    items: list[object] = []
    current = chain
    while is_chain(current):
        items.append(car(current))
        current = cdr(current)
    return items, current


def _get_form_item(form: object, index: int) -> object | None:
    """获取 form 的第 index 个元素。."""
    if is_chain(form):
        items = chain_to_list(form)
        return items[index] if index < len(items) else None
    return None


def _form_length(form: object) -> int:
    """获取 form 的长度。."""
    if is_chain(form):
        return len(chain_to_list(form))
    return 0


def _canonicalize_host_value(value: object) -> object:
    """Wrap raw Python ``int``/``float`` host literals in ``IntValue``/``FloatValue``.

    Forms constructed directly by the host (i.e. not produced by reader) may
    contain raw ``int``/``float`` atoms. The canonical Qy runtime number is
    ``NumberValue``, so we wrap them here at the HIR boundary. ``bool`` is left
    intact because Python ``bool`` is its own host literal kind.
    """
    from qy.sem.core import FloatValue
    from qy.sem.core import IntValue

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return IntValue(value)
    if isinstance(value, float):
        return FloatValue(value)
    return value


def _lower_symbol(
    symbol: Symbol,
    scope: Scope,
    context: LoweringContext,
    *,
    symbol_as_data: bool,
) -> IRExpr:
    if (binding := scope.lookup(symbol)) is not None:
        return SymbolRefExpr(symbol, binding, symbol.span)

    # ``symbol_as_data`` is set inside quote / quasiquote contexts, where the
    # symbol must remain a syntax datum and *not* be resolved to a runtime
    # value. Keep the LiteralExpr(symbol, "symbol") shape for that case.
    if symbol_as_data:
        return LiteralExpr(symbol, "symbol", symbol.span, symbol)

    literal_type_name = default_literal_type(symbol)
    if literal_type_name is not None:
        # Literal symbols (numbers, chars, strings, lisp truth values) stay as
        # ``SymbolRefExpr`` whose binding marks them as ``default-literal``.
        # Their value is resolved at runtime by walking the symbol-space chain
        # — number-ss / char-ss / string-ss / lisp-ss are real ssc nodes that
        # answer ``lookup(symbol)`` directly. No HIR-time materialization.
        binding = Binding(
            symbol,
            "default-literal",
            literal_type_name,
            owner_space=None,
            operator_kind=None,
            eager_arguments=True,
            value=None,
        )
        return SymbolRefExpr(symbol, binding, symbol.span)

    # Final fallback: the symbol is not a lexical binding and not a known
    # literal spelling, but the runtime environment may still know how to
    # resolve it (e.g. host injection via custom ``literal_resolver``).
    # Emit a SymbolRefExpr so MIR uses LOAD_ENV; the lookup is deferred to
    # ``RuntimeSpace.resolve`` which walks ssc + literal_resolver.
    try:
        resolved = context.env.resolve(symbol)
    except EvaluationError:
        resolved = None
        env_has_binding = False
    else:
        env_has_binding = True
    if env_has_binding:
        binding = Binding(
            symbol,
            "default-literal",
            value_type(resolved),
            owner_space=None,
            operator_kind=operator_kind_for_value(resolved),
            eager_arguments=value_uses_eager_arguments(resolved),
            value=resolved,
        )
        return SymbolRefExpr(symbol, binding, symbol.span)

    context.diagnostic(f"unresolved symbol {symbol.name!r}", symbol)
    return UnresolvedSymbolExpr(symbol, symbol.span)


def _lower_quote(args: tuple[object, ...], context: LoweringContext, form: object) -> IRExpr:
    if len(args) != 1:
        context.diagnostic(f"quote expects exactly one argument, got {len(args)}", form)
        return QuoteExpr(nil, get_span(form))
    return QuoteExpr(cast(Form, args[0]), get_span(form))


def _lower_quasiquote(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
    *,
    tail: bool = False,
) -> IRExpr:
    if len(args) != 1:
        context.diagnostic(f"quasiquote expects exactly one argument, got {len(args)}", form)
        return QuoteExpr(nil, get_span(form))
    expanded = expand_quasiquote(args[0])
    return _lower_form(expanded, scope, context, tail=tail)


def _lower_eval(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    if len(args) != 1:
        context.diagnostic(f"eval expects exactly one argument, got {len(args)}", form)
        expression = LiteralExpr(None, "none", get_span(form))
    else:
        expression = _lower_form(args[0], scope, context)
    return RuntimeEvalExpr(expression, get_span(form))


def _lower_macro(
    form: object,
    scope: Scope,
    context: LoweringContext,
) -> IRExpr:
    items = _form_to_list(form)
    if len(items) < 4:
        context.diagnostic("macro expects a name, parameter list, and body", form)
        return MacroExpr(Symbol("<invalid>"), (), (), (), get_span(form))
    _, name, params, *body = items
    name = _ensure_symbol(name, "macro name", context)
    param_symbols = _parameter_symbols(params, "macro", context)
    macro_scope = _define_parameters(scope.child(f"macro:{name.name}"), param_symbols, context)
    macro_scope = _define_local(
        macro_scope,
        Binding(Symbol("gensym"), "builtin", "operator", macro_scope.symbol_space, "pure"),
        context,
    )
    macro_scope = _define_local(
        macro_scope,
        Binding(Symbol("capture"), "builtin", "operator", macro_scope.symbol_space, "pure"),
        context,
    )
    lowered_body = _lower_body(tuple(body), macro_scope, context)
    return MacroExpr(name, param_symbols, lowered_body, tuple(body), get_span(form))


def _lower_cond(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
    *,
    tail: bool,
) -> IRExpr:
    clauses: list[CondClause] = []
    result_type: TypeName = "none"
    for clause in args:
        clause_items = _form_to_list(clause)
        if len(clause_items) != 2:
            context.diagnostic(f"cond clause must be a pair, got {clause!r}", clause)
            continue
        condition = _lower_form(clause_items[0], scope, context)
        result = _lower_form(clause_items[1], scope, context, tail=tail)
        result_type = _type_of(result)
        clauses.append(CondClause(condition, result))
    return CondExpr(tuple(clauses), get_span(form), result_type)


def _lower_let(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
    *,
    tail: bool,
) -> IRExpr:
    if len(args) < 2:
        context.diagnostic("let expects bindings and at least one body expression", form)
        return LetExpr((), (), get_span(form), "unknown")
    bindings_form, *body = args

    # 接受 Chain 或 nil 作为绑定列表
    if not (is_chain(bindings_form) or is_nil(bindings_form)):
        context.diagnostic(f"let bindings must be a list, got {bindings_form!r}", bindings_form)
        return LetExpr(
            (),
            _lower_body(tuple(body), scope.child("let:error"), context, tail=tail),
            get_span(form),
        )

    bindings_list = _form_to_list(bindings_form) if not is_nil(bindings_form) else []
    local_scope = scope.child("let")
    bindings: list[LetBinding] = []
    for binding_form in bindings_list:
        binding_items = _form_to_list(binding_form)
        if len(binding_items) != 2:
            context.diagnostic(f"let binding must be a pair, got {binding_form!r}", binding_form)
            continue
        name, value_form = binding_items[0], binding_items[1]
        name = _ensure_symbol(name, "let binding name", context)
        value = _lower_form(value_form, local_scope, context)
        bindings.append(LetBinding(name, value))
        local_scope = _define_local(
            local_scope,
            Binding(name, "let-binding", _type_of(value), local_scope.symbol_space),
            context,
        )

    lowered_body = _lower_body(tuple(body), local_scope, context, tail=tail)
    return LetExpr(
        tuple(bindings),
        lowered_body,
        get_span(form),
        _body_type(lowered_body),
        space=local_scope.symbol_space,
    )


def _lower_lambda(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    if len(args) < 2:
        context.diagnostic("lambda expects a parameter list and body", form)
        return LambdaExpr((), (), get_span(form))
    params, *body = args
    param_symbols, rest_param = _parameter_symbols_and_rest(params, "lambda", context)
    function_scope = _define_parameters(scope.child("lambda"), param_symbols, context)
    function_scope = _define_rest_parameter(function_scope, rest_param, context)
    return LambdaExpr(
        param_symbols,
        _lower_body(tuple(body), function_scope, context, tail=True),
        get_span(form),
        space=function_scope.symbol_space,
        rest_param=rest_param,
    )


def _lower_component(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    """Lower component 算子调用。.

    component 目前由 MetaOperator 实现（返回宏），这里按普通调用 lower。
    我们将其 lower 为一个普通的函数调用。
    """
    component_symbol = Symbol("component")
    component_ref = scope.lookup(component_symbol)

    if len(args) < 2:
        context.diagnostic("component expects at least 2 operators", form)
        if component_ref is None:
            return UnresolvedSymbolExpr(component_symbol, get_span(form))
        return CallExpr(
            SymbolRefExpr(component_symbol, component_ref, get_span(form)),
            (),
            get_span(form),
            "function",
        )

    # Lower 所有算子参数
    lowered_args = tuple(_lower_form(arg, scope, context) for arg in args)

    # 创建对 component 算子的调用
    if component_ref is None:
        context.diagnostic("unresolved symbol 'component'", form)
        return UnresolvedSymbolExpr(component_symbol, get_span(form))

    return CallExpr(
        SymbolRefExpr(component_symbol, component_ref, get_span(form)),
        lowered_args,
        get_span(form),
        "function",
    )


def _lower_defun(
    form: object,
    scope: Scope,
    context: LoweringContext,
) -> IRExpr:
    items = _form_to_list(form)
    if len(items) < 4:
        context.diagnostic("defun expects a name, parameter list, and body", form)
        return DefineExpr(Symbol("<invalid>"), LambdaExpr((), (), get_span(form)), get_span(form))
    _, name, params, *body = items
    name = _ensure_symbol(name, "defun name", context)
    param_symbols, rest_param = _parameter_symbols_and_rest(params, "defun", context)
    function_scope = _define_local(
        scope.child(f"defun:{name.name}"),
        Binding(name, "defun", "function", scope.symbol_space),
        context,
    )
    function_scope = _define_parameters(function_scope, param_symbols, context)
    function_scope = _define_rest_parameter(function_scope, rest_param, context)
    return DefineExpr(
        name,
        LambdaExpr(
            param_symbols,
            _lower_body(tuple(body), function_scope, context, tail=True),
            get_span(form),
            space=function_scope.symbol_space,
            rest_param=rest_param,
        ),
        get_span(form),
        owner_space=scope.symbol_space,
    )


def _lower_defeffect(form: object, scope: Scope, context: LoweringContext) -> IRExpr:
    items = _form_to_list(form)
    if len(items) < 2:
        context.diagnostic("defeffect expects an effect name", form)
        return DefineExpr(
            Symbol("<invalid>"),
            DefeffectExpr(Symbol("<invalid>"), True, get_span(form)),
            get_span(form),
        )
    _, name, *options = items
    name = _ensure_symbol(name, "defeffect name", context)
    resumable = True
    if options:
        if (
            len(options) != 2
            or options[0] != Symbol(":resumable")
            or options[1]
            not in {
                Symbol("true"),
                Symbol("false"),
            }
        ):
            context.diagnostic("defeffect options must be empty or :resumable true|false", form)
        else:
            resumable = options[1] == Symbol("true")
    return DefineExpr(
        name,
        DefeffectExpr(name, resumable, get_span(form)),
        get_span(form),
        owner_space=scope.symbol_space,
    )


def _lower_module(
    form: object,
    scope: Scope,
    context: LoweringContext,
) -> IRExpr:
    items = _form_to_list(form)
    if len(items) < 2:
        context.diagnostic("module expects a name and body", form)
        return ModuleExpr(Symbol("<invalid>"), (), (), get_span(form))
    _, name, *body = items
    name = _ensure_symbol(name, "module name", context)
    export_names: list[Symbol] = []
    module_scope = _predeclare_callable_definitions(
        tuple(body), scope.child(f"module:{name.name}"), context
    )
    lowered_body: list[IRExpr] = []
    for expression in body:
        if _is_special_form(expression, "exports"):
            expr_items = _form_to_list(expression)
            for item in expr_items[1:]:
                if isinstance(item, Symbol):
                    export_names.append(item)
                else:
                    sub_items = _form_to_list(item)
                    for sub in sub_items:
                        if isinstance(sub, Symbol):
                            export_names.append(sub)
            continue
        lowered = _lower_form(expression, module_scope, context)
        lowered_body.append(lowered)
        module_scope = _scope_after_form(expression, lowered, module_scope, context)
    return ModuleExpr(
        name,
        tuple(lowered_body),
        tuple(export_names),
        get_span(form),
        space=module_scope.symbol_space,
        macro_exports=module_macro_names(context.env, name.name),
    )


def _lower_from(form: object, context: LoweringContext) -> IRExpr:
    try:
        module_name, specs = parse_from_import(form)
    except ValueError as e:
        context.diagnostic(str(e), form)
        return FromImportExpr(Symbol("<invalid>"), (), get_span(form))

    try:
        source_module = resolve_known_module(module_name.name, context.env)
    except KeyError as e:
        context.diagnostic(str(e), form)
        return FromImportExpr(module_name, specs, get_span(form))

    for name in missing_export_names(specs, source_module):
        context.diagnostic(f"module {module_name.name!r} has no export {name.name!r}", name)
    return FromImportExpr(module_name, specs, get_span(form))


def _lower_perform(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    if len(args) != 2:
        context.diagnostic(f"perform expects exactly two arguments, got {len(args)}", form)
        return PerformExpr(
            Symbol("<invalid>"), LiteralExpr(None, "none", get_span(form)), get_span(form)
        )
    effect, arg = args
    effect = _ensure_symbol(effect, "perform effect name", context)
    if not _effect_is_declared(effect, scope, context):
        context.diagnostic(
            f"effect {effect.name!r} is not declared; add defeffect before perform", effect
        )
    return PerformExpr(effect, _lower_form(arg, scope, context), get_span(form))


def _lower_handle(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
    *,
    tail: bool,
) -> IRExpr:
    if len(args) != 2:
        context.diagnostic(f"handle expects exactly two arguments, got {len(args)}", form)
        return HandleExpr(LiteralExpr(None, "none", get_span(form)), (), get_span(form))

    # 支持两种 handle 格式:
    #   标准格式: (handle expression ((effect (arg k) body...) ...))
    #   on 格式:  (handle (on effect (arg k) body...) expression)
    first, second = args
    if _is_on_form(first):
        # on 格式: 第一个参数是 on 形式的 handler, 第二个是 expression
        expression = second
        handlers_form = first
    else:
        # 标准格式: 第一个参数是 expression, 第二个是 handler 列表
        expression = first
        handlers_form = second

    # 收集 on 格式中的 effect 名并自动声明未声明的 effect
    if _is_on_form(handlers_form):
        scope = _auto_declare_on_effects(handlers_form, scope, context)

    lowered_expression = _lower_form(expression, scope, context, tail=tail)
    handlers: list[EffectHandler] = []

    # 接受 Chain 或 nil 作为 handler 列表
    if _is_on_form(handlers_form):
        # on 格式: (on effect (arg k) body...) 形式
        handlers_list = [handlers_form]
    elif not (is_chain(handlers_form) or is_nil(handlers_form)):
        context.diagnostic(f"handle clauses must be a list, got {handlers_form!r}", handlers_form)
        return HandleExpr(lowered_expression, (), get_span(form), _type_of(lowered_expression))
    else:
        handlers_list = _form_to_list(handlers_form) if not is_nil(handlers_form) else []

    result_type = _type_of(lowered_expression)
    for clause in handlers_list:
        clause_items = _form_to_list(clause)
        # 检测 on 格式: (on effect-name (arg k) body...)
        is_on_clause = (
            len(clause_items) >= 4
            and isinstance(clause_items[0], Symbol)
            and clause_items[0].name == "on"
        )
        if is_on_clause:
            _, effect, params, *body = clause_items
        elif len(clause_items) >= 3:
            effect, params, *body = clause_items
        else:
            context.diagnostic(
                f"handle clause must be (effect (arg k) body...), got {clause!r}", clause
            )
            continue
        effect = _ensure_symbol(effect, "handle effect name", context)
        if not _effect_is_declared(effect, scope, context):
            context.diagnostic(
                f"effect {effect.name!r} is not declared; add defeffect before handle", effect
            )
        # on 格式中 () 表示使用默认的 (v k) 参数
        if is_on_clause and is_nil(params):
            param_symbols = (Symbol("_v"), Symbol("k"))
        else:
            param_symbols = _parameter_symbols(params, "handle", context)
        # on 格式支持 (on effect (value) k body...): k 作为独立 symbol 跟在参数列表后
        if is_on_clause and len(param_symbols) == 1 and body and isinstance(body[0], Symbol):
            param_symbols = (param_symbols[0], body[0])
            body = body[1:]
        if len(param_symbols) != 2:
            context.diagnostic(f"handle parameters must be (arg k), got {params!r}", params)
            continue
        handler_scope = scope.child(f"handle:{effect.name}")
        handler_scope = _define_parameters(handler_scope, param_symbols, context)
        lowered_body = _lower_body(tuple(body), handler_scope, context, tail=tail)
        result_type = _body_type(lowered_body)
        handlers.append(
            EffectHandler(
                effect,
                param_symbols[0],
                param_symbols[1],
                lowered_body,
                auto_declared=is_on_clause,
            )
        )
    return HandleExpr(lowered_expression, tuple(handlers), get_span(form), result_type)


def _is_on_form(form: object) -> bool:
    """检查 form 是否为 (on effect-name (arg k) body...) 形式."""
    if not is_chain(form):
        return False
    head = car(form)
    return isinstance(head, Symbol) and head.name == "on"


def _auto_declare_on_effects(
    on_form: object,
    scope: Scope,
    context: LoweringContext,
) -> Scope:
    """从 (on effect-name ...) 形式中收集 effect 名, 自动声明未声明的 effect."""
    items = _form_to_list(on_form)
    if len(items) >= 3 and isinstance(items[0], Symbol) and items[0].name == "on":
        effect_name = _ensure_symbol(items[1], "handle effect name", context)
        if not _effect_is_declared(effect_name, scope, context):
            scope = _define_local(
                scope, Binding(effect_name, "defeffect", "effect", scope.symbol_space), context
            )
    return scope


def _lower_resume(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    if len(args) != 2:
        context.diagnostic(f"resume expects exactly two arguments, got {len(args)}", form)
        return ResumeExpr(
            LiteralExpr(None, "none", get_span(form)),
            LiteralExpr(None, "none", get_span(form)),
            get_span(form),
        )
    return ResumeExpr(
        _lower_form(args[0], scope, context),
        _lower_form(args[1], scope, context),
        get_span(form),
    )


def _lower_assert(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    if len(args) not in {1, 2}:
        context.diagnostic(f"assert expects one or two arguments, got {len(args)}", form)
    condition = (
        _lower_form(args[0], scope, context) if args else LiteralExpr(False, "bool", get_span(form))
    )
    message = _lower_form(args[1], scope, context) if len(args) > 1 else None
    return AssertExpr(condition, message, get_span(form), _type_of(condition))


def _lower_body(
    body: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    *,
    tail: bool = False,
) -> tuple[IRExpr, ...]:
    if not body:
        context.diagnostic("body must contain at least one expression")
        return ()
    lowered: list[IRExpr] = []
    body_scope = _predeclare_callable_definitions(body, scope, context)
    for index, expression in enumerate(body):
        item = _lower_form(
            expression,
            body_scope,
            context,
            tail=tail and index == len(body) - 1,
        )
        lowered.append(item)
        body_scope = _scope_after_form(expression, item, body_scope, context)
    return tuple(lowered)


def _scope_after_form(
    form: object,
    expr: IRExpr,
    scope: Scope,
    context: LoweringContext,
    *,
    emit: bool = True,
) -> Scope:
    items = _form_to_list(form)
    if len(items) < 2:
        return scope

    operator = items[0]
    name = items[1]

    if operator == Symbol("pipeline") and isinstance(expr, PipelineExpr):
        # pipeline 是 begin/end 序列，不创建新的 symbol-space；其 body 中
        # define / defun / defeffect 的 binding 必须泄漏到外层 scope。
        # 内部 lowering 已经发过诊断，这里只做 scope 记账。
        pipeline_scope = scope
        for sub_form, sub_expr in zip(items[1:], expr.body, strict=True):
            pipeline_scope = _scope_after_form(
                sub_form, sub_expr, pipeline_scope, context, emit=False
            )
        return pipeline_scope

    if operator == Symbol("defun") and isinstance(name, Symbol):
        # defun 已经被前向声明，允许覆盖
        return _define_local(
            scope,
            Binding(name, "defun", "function", scope.symbol_space),
            context,
            allow_redefinition=True,
            emit=emit,
        )
    if operator == Symbol("define") and isinstance(name, Symbol):
        # Strip quoted-symbol prefix for scope registration
        actual_name = (
            Symbol(name.name[1:]) if name.name.startswith("'") and len(name.name) > 1 else name
        )
        # define 的 binding 类型应该是其 value 的类型，而不是 DefineExpr 本身的类型
        inferred = _type_of(expr.value) if isinstance(expr, DefineExpr) else "any"
        # 如果是 define + lambda 且已前向声明，允许覆盖
        allow_redef = scope.has_local(actual_name) and inferred == "function"
        return _define_local(
            scope,
            Binding(actual_name, "define", inferred, scope.symbol_space),
            context,
            allow_redefinition=allow_redef,
            emit=emit,
        )
    if operator == Symbol("defeffect") and isinstance(name, Symbol):
        return _define_local(
            scope,
            Binding(name, "defeffect", "effect", scope.symbol_space),
            context,
            allow_redefinition=True,
        )
    if (
        operator == Symbol("bind")
        and isinstance(name, Symbol)
        and name.name.startswith("'")
        and len(name.name) > 1
    ):
        actual_name = Symbol(name.name[1:])
        return _define_local(
            scope,
            Binding(actual_name, "define", "any", scope.symbol_space),
            context,
            emit=emit,
        )
    if operator == Symbol("bind") and is_chain(name):
        quote_items = _form_to_list(name)
        if (
            len(quote_items) == 2
            and quote_items[0] == Symbol("quote")
            and isinstance(quote_items[1], Symbol)
        ):
            return _define_local(
                scope,
                Binding(quote_items[1], "define", "any", scope.symbol_space),
                context,
                emit=emit,
            )
    if operator == Symbol("macro") and isinstance(name, Symbol):
        return _define_local(
            scope,
            Binding(
                name, "macro-param", "operator", scope.symbol_space, "meta", eager_arguments=False
            ),
            context,
            emit=emit,
        )
    if operator == Symbol("module") and isinstance(name, Symbol):
        remember_source_module(form, context.env)
        return _define_local(
            scope, Binding(name, "module", "any", scope.symbol_space), context, emit=emit
        )
    if operator != Symbol("from"):
        return scope

    try:
        module_name, specs = parse_from_import(form)
        source_module = resolve_known_module(module_name.name, context.env)
    except (KeyError, ValueError):
        return scope

    next_scope = scope
    # 与运行时 fold / provisional module 共用同一选择原语。
    for alias, value, _is_macro in iter_selected_exports(
        module_name.name, specs, source_module, require=False
    ):
        next_scope = _define_local(
            next_scope,
            Binding(
                alias,
                "import",
                value_type(value),
                next_scope.symbol_space,
                operator_kind=operator_kind_for_value(value),
                eager_arguments=value_uses_eager_arguments(value),
                value=value,
            ),
            context,
            emit=emit,
        )
    return next_scope


def _predeclare_callable_definitions(
    body: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
) -> Scope:
    """前向声明 defun 和 (define name (lambda ...))，不检查重复。."""
    next_scope = scope
    for expression in body:
        items = _form_to_list(expression)
        if len(items) < 2:
            continue
        # 处理 defun
        if items[0] == Symbol("defun"):
            name = items[1]
            if isinstance(name, Symbol):
                # 直接 define，不通过 _define_local（避免重复检查）
                next_scope = next_scope.define(
                    Binding(name, "defun", "function", next_scope.symbol_space)
                )
        # 处理 (define name (lambda ...))
        elif items[0] == Symbol("define") and len(items) >= 3:
            name = items[1]
            value_form = items[2]
            if isinstance(name, Symbol) and _is_lambda_form(value_form):
                # 直接 define，不通过 _define_local（避免重复检查）
                next_scope = next_scope.define(
                    Binding(name, "define", "function", next_scope.symbol_space)
                )
    return next_scope


def _is_lambda_form(form: object) -> bool:
    """检查 form 是否是 lambda 表达式。."""
    items = _form_to_list(form)
    return len(items) > 0 and items[0] == Symbol("lambda")


def _define_local(
    scope: Scope,
    binding: Binding,
    context: LoweringContext,
    *,
    allow_redefinition: bool = False,
    emit: bool = True,
) -> Scope:
    """在当前 scope 定义 binding。.

    Args:
        scope: 当前作用域
        binding: 要定义的符号绑定
        context: Lowering 上下文
        allow_redefinition: 如果为 True，允许覆盖已存在的 binding（用于前向声明后的实际定义）
        emit: 是否发出诊断；pipeline 泄漏 scope 记账时为 False，避免重复诊断
    """
    if emit and scope.has_local(binding.symbol) and not allow_redefinition:
        context.diagnostic(
            f"symbol {binding.symbol.name!r} is already bound in this scope", binding.symbol
        )
    # Ensure binding has the current scope's symbol_space as owner
    if binding.owner_space is None and scope.symbol_space is not None:
        binding = Binding(
            binding.symbol,
            binding.source,
            binding.type_name,
            scope.symbol_space,
            operator_kind=binding.operator_kind,
            eager_arguments=binding.eager_arguments,
            continuous=binding.continuous,
            value=binding.value,
        )
    # Record the symbol -> slot assignment in the owner space. This is the
    # HIR-level layout fact that ``resolve.spaces`` turns into a serializable
    # layout; without it ``SymbolSpace.bindings`` stays empty forever.
    space = binding.owner_space
    if space is not None and binding.symbol not in space.bindings:
        space.bindings[binding.symbol] = len(space.bindings)
        space.sources[binding.symbol.name] = binding.source
    return scope.define(binding)


def _define_parameters(scope: Scope, params: tuple[Symbol, ...], context: LoweringContext) -> Scope:
    next_scope = scope
    for param in params:
        next_scope = _define_local(
            next_scope,
            Binding(param, "lambda-param", "any", scope.symbol_space),
            context,
        )
    return next_scope


def _define_rest_parameter(
    scope: Scope,
    rest_param: Symbol | None,
    context: LoweringContext,
) -> Scope:
    if rest_param is None:
        return scope
    return _define_local(
        scope,
        Binding(rest_param, "lambda-param", "any", scope.symbol_space),
        context,
    )


def _parameter_symbols_and_rest(
    params: object,
    context_name: str,
    context: LoweringContext,
) -> tuple[tuple[Symbol, ...], Symbol | None]:
    """解析参数列表，识别 `&rest` / `&body` 变参名（其余仍要求是 symbol）。."""
    if is_chain(params) or is_nil(params):
        params_list = _form_to_list(params) if not is_nil(params) else []
    else:
        context.diagnostic(f"{context_name} parameters must be a list, got {params!r}", params)
        return ((), None)

    fixed: list[Symbol] = []
    rest_param: Symbol | None = None
    index = 0
    while index < len(params_list):
        param = params_list[index]
        if not isinstance(param, Symbol):
            context.diagnostic(f"{context_name} parameter must be a symbol, got {param!r}", param)
            index += 1
            continue
        if param.name in ("&rest", "&body"):
            if index + 1 >= len(params_list):
                context.diagnostic(f"{context_name} {param.name} requires a parameter name", param)
                break
            if index + 2 < len(params_list):
                context.diagnostic(f"{context_name} {param.name} must be the last parameter", param)
            candidate = params_list[index + 1]
            if not isinstance(candidate, Symbol):
                context.diagnostic(
                    f"{context_name} rest parameter must be a symbol, got {candidate!r}", candidate
                )
                break
            rest_param = candidate
            break
        fixed.append(param)
        index += 1
    return (tuple(fixed), rest_param)


def _parameter_symbols(
    params: object,
    context_name: str,
    context: LoweringContext,
) -> tuple[Symbol, ...]:
    # 接受 Chain 或 nil 作为参数列表
    if is_chain(params) or is_nil(params):
        params_list = _form_to_list(params) if not is_nil(params) else []
    else:
        context.diagnostic(f"{context_name} parameters must be a list, got {params!r}", params)
        return ()

    result: list[Symbol] = []
    for param in params_list:
        if not isinstance(param, Symbol):
            context.diagnostic(f"{context_name} parameter must be a symbol, got {param!r}", param)
            continue
        result.append(param)
    return tuple(result)


def _ensure_symbol(value: object, context_name: str, context: LoweringContext) -> Symbol:
    if isinstance(value, Symbol):
        return value
    context.diagnostic(f"{context_name} must be a symbol, got {value!r}", value)
    return Symbol("<invalid>")


def _effect_is_declared(effect: Symbol, scope: Scope, context: LoweringContext) -> bool:
    if (binding := scope.lookup(effect)) is not None:
        return binding.type_name == "effect"
    try:
        return value_type(context.env.resolve(effect)) == "effect"
    except EvaluationError:
        return False


def _call_uses_non_eager_arguments(operator: IRExpr) -> bool:
    return (
        isinstance(operator, SymbolRefExpr)
        and operator.binding.type_name == "operator"
        and not operator.binding.eager_arguments
    )


def _argument_is_eager(operator: IRExpr, index: int) -> bool:
    """Decide if argument at `index` should be evaluated (vs. passed as datum).

    Per-arg policy comes from the operator signature when available.
    Fall back to the operator's overall eager_arguments flag.
    """
    signature = _operator_signature(operator)
    if signature is not None and signature.argument_policy:
        policy = signature.argument_policy
        if index < len(policy):
            return policy[index] == "eager"
    if isinstance(operator, SymbolRefExpr):
        return operator.binding.eager_arguments
    return True


def _infer_call_type(
    operator: object,
    args: tuple[IRExpr, ...],
    operator_expr: IRExpr,
    context: LoweringContext,
    form: object,
) -> TypeName:
    signature = _operator_signature(operator_expr)
    if signature is not None:
        name = operator.name if isinstance(operator, Symbol) else "call"
        if not signature.arity.accepts(len(args)):
            context.diagnostic(
                _arity_message(
                    name,
                    signature,
                    len(args),
                ),
                form,
            )
        for index, arg in enumerate(args):
            expected = _signature_argument_type(signature, index)
            if expected is not None and _type_of(arg) not in {expected, "unknown", "any"}:
                context.diagnostic(
                    f"{name} expects {expected} arguments, got {_type_of(arg)}",
                    form,
                )
        return signature.return_type

    if isinstance(operator, Symbol):
        match operator.name:
            case "+" | "-" | "*" | "/":
                for arg in args:
                    if _type_of(arg) not in {"number", "unknown", "any"}:
                        context.diagnostic(
                            f"{operator.name} expects number arguments, got {_type_of(arg)}",
                            form,
                        )
                return "number"

    operator_type = _type_of(operator_expr)
    # "any" 表示静态类型未知（例如 lambda 参数没有类型标注）。Qy 是动态语言，
    # 只有确知不是 callable 时才报错；否则必须允许把函数值当 operator 调用。
    if operator_type not in {"operator", "function", "unknown", "any"}:
        context.diagnostic(f"operator position is {operator_type}, not callable", form)
    return "any"


def _operator_signature(operator: IRExpr) -> OperatorSignature | None:
    if isinstance(operator, SymbolRefExpr):
        value = operator.binding.value
        signature = getattr(value, "signature", None) if value is not None else None
        if signature is None:
            signature = lookup_operator_signature(operator.symbol.name)
        return signature
    return None


def _arity_message(name: str, signature: OperatorSignature, actual: int) -> str:
    return format_arity_message(name, signature, actual)


def _signature_argument_type(signature: OperatorSignature, index: int) -> TypeName | None:
    try:
        return signature.argument_types[index]
    except IndexError:
        return signature.rest_type


def _type_of(expr: IRExpr) -> TypeName:
    return expr.type_name


def _body_type(body: tuple[IRExpr, ...]) -> TypeName:
    if not body:
        return "unknown"
    return _type_of(body[-1])


def _is_special_form(form: object, name: str) -> bool:
    if is_chain(form):
        items = chain_to_list(form)
        return len(items) > 0 and items[0] == Symbol(name)
    return False


def _lower_define(form: object, scope: Scope, context: LoweringContext) -> IRExpr:
    items = _form_to_list(form)
    if len(items) < 3:
        context.diagnostic("define expects a name and a value", form)
        return DefineExpr(
            Symbol("<invalid>"), LiteralExpr(None, "none", get_span(form)), get_span(form)
        )
    _, name_form, value_form = items[0], items[1], items[2]
    if isinstance(name_form, Symbol) and name_form.name.startswith("'") and len(name_form.name) > 1:
        name = Symbol(name_form.name[1:])
    else:
        name = _ensure_symbol(name_form, "define name", context)
    value = _lower_form(value_form, scope, context)
    return DefineExpr(name, value, get_span(form), _type_of(value), owner_space=scope.symbol_space)


def _lower_pipeline(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
    *,
    tail: bool = False,
) -> IRExpr:
    if not args:
        context.diagnostic("pipeline expects at least one expression", form)
        return LiteralExpr(None, "none", get_span(form))
    # pipeline 是 begin/end 语义的同一 symbol-space 序列：define / defun /
    # defeffect 的 binding 必须对后续 pipeline 表达式可见（与 body 一致）。
    body_scope = _predeclare_callable_definitions(args, scope, context)
    lowered: list[IRExpr] = []
    for i, arg in enumerate(args):
        item = _lower_form(arg, body_scope, context, tail=tail and i == len(args) - 1)
        lowered.append(item)
        body_scope = _scope_after_form(arg, item, body_scope, context)
    return PipelineExpr(tuple(lowered), get_span(form))


def _lower_parallel(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    lowered = tuple(_lower_form(arg, scope, context) for arg in args)
    return ParallelExpr(lowered, get_span(form))


def _lower_all(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    lowered = tuple(_lower_form(arg, scope, context) for arg in args)
    return AllExpr(lowered, get_span(form))


def _lower_race(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    lowered = tuple(_lower_form(arg, scope, context) for arg in args)
    return RaceExpr(lowered, get_span(form))


def _lower_apply(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    if len(args) != 2:
        context.diagnostic("apply expects a function and an argument list", form)
        return LiteralExpr(None, "none", get_span(form))
    func_expr = _lower_form(args[0], scope, context)
    args_expr = _lower_form(args[1], scope, context)
    return ApplyExpr(func_expr, args_expr, get_span(form))


def _lower_cache(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: object,
) -> IRExpr:
    if len(args) != 1:
        context.diagnostic("cache expects exactly one expression", form)
        return LiteralExpr(None, "none", get_span(form))
    expression = _lower_form(args[0], scope, context)
    try:
        cache_key = args[0]
        hash(cache_key)
    except TypeError:
        cache_key = repr(args[0])
    return CacheExpr(expression, cache_key, get_span(form))
