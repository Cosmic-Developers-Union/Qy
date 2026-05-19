# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.diagnostics import Diagnostic
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
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
from qy.ir import UnresolvedSymbolExpr
from qy.literals import default_literal_type
from qy.literals import try_default_literal
from qy.operator_signature import OperatorSignature
from qy.operator_signature import format_arity_message
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.semantics import literal_type
from qy.semantics import operator_kind_for_value
from qy.semantics import value_type
from qy.semantics import value_uses_eager_arguments
from qy.source_modules import remember_source_module
from qy.source_modules import resolve_known_module
from qy.stdlib.imports import parse_from_import
from qy.types import TypeName

__all__ = [
    "LoweringContext",
    "Scope",
    "lower",
    "lower_source",
]


@dataclass(frozen=True, slots=True)
class Scope:
    bindings: dict[Symbol, Binding] | None = None
    parent: Scope | None = None

    def child(self) -> Scope:
        return Scope(parent=self)

    def define(self, binding: Binding) -> Scope:
        bindings = dict(self.bindings or {})
        bindings[binding.symbol] = binding
        return Scope(bindings, self.parent)

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

    @classmethod
    def create(cls, env: Environment | None = None) -> LoweringContext:
        return cls(env or standard_environment(), [])

    def diagnostic(self, message: str, form: object | None = None) -> None:
        span = get_span(form) if form is not None else None
        self.diagnostics.append(
            Diagnostic(
                message,
                line=None if span is None else span.line,
                column=None if span is None else span.column,
            )
        )


def lower_source(
    source: str, env: Environment | None = None, *, source_name: str | None = None
) -> ProgramIR:
    try:
        forms = read(source, source_name=source_name)
    except ReaderSyntaxError as e:
        return ProgramIR(
            (),
            (Diagnostic(str(e), "error", line=e.line, column=e.column),),
        )
    return lower(forms, env)


def lower(forms: list[Form], env: Environment | None = None) -> ProgramIR:
    context = LoweringContext.create(env)
    scope = _scope_from_environment(context.env)
    scope = _predeclare_callable_definitions(tuple(forms), scope, context)
    body: list[IRExpr] = []
    for index, form in enumerate(forms):
        expr = _lower_form(form, scope, context, tail=index == len(forms) - 1)
        body.append(expr)
        scope = _scope_after_form(form, expr, scope, context)
    return ProgramIR(tuple(body), tuple(context.diagnostics))


def _scope_from_environment(env: Environment) -> Scope:
    scope = Scope()
    all_visible = {**env.bindings(), **env.hidden_bindings()}
    for symbol, value in all_visible.items():
        scope = scope.define(
            Binding(
                symbol,
                "global",
                value_type(value),
                operator_kind_for_value(value),
                value_uses_eager_arguments(value),
                value,
            )
        )
    return scope


def _lower_form(
    form: object,
    scope: Scope,
    context: LoweringContext,
    *,
    tail: bool = False,
    symbol_as_data: bool = False,
) -> IRExpr:
    if isinstance(form, Symbol):
        return _lower_symbol(form, scope, context, symbol_as_data=symbol_as_data)
    if isinstance(form, DottedTuple):
        context.diagnostic("dotted form cannot be evaluated as a call", form)
        return LiteralExpr(form, "unknown", get_span(form))
    if not isinstance(form, tuple):
        return LiteralExpr(form, literal_type(form), get_span(form))
    if not form:
        return LiteralExpr(form, "nil", get_span(form))

    operator = form[0]
    args = tuple(form[1:])
    if isinstance(operator, Symbol):
        match operator.name:
            case "quote":
                return _lower_quote(args, context, form)
            case "quasiquote":
                return _lower_quasiquote(args, scope, context, form, tail=tail)
            case "eval":
                return _lower_eval(args, scope, context, form)
            case "macro":
                return _lower_macro(form, scope, context)
            case "cond":
                return _lower_cond(args, scope, context, form, tail=tail)
            case "let":
                return _lower_let(args, scope, context, form, tail=tail)
            case "lambda":
                return _lower_lambda(args, scope, context, form)
            case "defun":
                return _lower_defun(form, scope, context)
            case "defeffect":
                return _lower_defeffect(form, context)
            case "module":
                return _lower_module(form, scope, context)
            case "from":
                return _lower_from(form, context)
            case "perform":
                return _lower_perform(args, scope, context, form)
            case "handle":
                return _lower_handle(args, scope, context, form, tail=tail)
            case "resume":
                return _lower_resume(args, scope, context, form)
            case "assert":
                return _lower_assert(args, scope, context, form)
            case "define":
                return _lower_define(form, scope, context)
            case "pipeline":
                return _lower_pipeline(args, scope, context, form, tail=tail)
            case "parallel":
                return _lower_parallel(args, scope, context, form)
            case "all":
                return _lower_all(args, scope, context, form)
            case "race":
                return _lower_race(args, scope, context, form)
            case "apply":
                return _lower_apply(args, scope, context, form)
            case "cache":
                return _lower_cache(args, scope, context, form)

    operator_expr = _lower_form(operator, scope, context)
    if isinstance(operator_expr, SymbolRefExpr) and operator_expr.binding.operator_kind == "meta":
        context.diagnostic(
            f"meta operator {operator_expr.symbol.name!r} can only run during macro expansion",
            form,
        )
        return UnresolvedSymbolExpr(operator_expr.symbol, get_span(form))

    args_as_data = _call_uses_non_eager_arguments(operator_expr)
    lowered_args = tuple(
        _lower_form(arg, scope, context, symbol_as_data=args_as_data) for arg in args
    )
    return CallExpr(
        operator_expr,
        lowered_args,
        get_span(form),
        _infer_call_type(operator, tuple(lowered_args), operator_expr, context, form),
        tail,
    )


def _lower_symbol(
    symbol: Symbol,
    scope: Scope,
    context: LoweringContext,
    *,
    symbol_as_data: bool,
) -> IRExpr:
    if (binding := scope.lookup(symbol)) is not None:
        return SymbolRefExpr(symbol, binding, symbol.span)

    literal_type_name = default_literal_type(symbol)
    if literal_type_name is not None:
        value = try_default_literal(symbol)
        return LiteralExpr(
            value,
            literal_type_name,
            symbol.span,
            symbol,
        )

    if symbol_as_data:
        return LiteralExpr(symbol, "symbol", symbol.span, symbol)

    try:
        resolved = context.env.resolve(symbol)
        return LiteralExpr(resolved, value_type(resolved), symbol.span, symbol)
    except EvaluationError:
        pass

    context.diagnostic(f"unresolved symbol {symbol.name!r}", symbol)
    return UnresolvedSymbolExpr(symbol, symbol.span)


def _lower_quote(
    args: tuple[object, ...], context: LoweringContext, form: tuple[object, ...]
) -> IRExpr:
    if len(args) != 1:
        context.diagnostic(f"quote expects exactly one argument, got {len(args)}", form)
        return QuoteExpr((), get_span(form))
    return QuoteExpr(cast(Form, args[0]), get_span(form))


def _lower_quasiquote(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
    *,
    tail: bool = False,
) -> IRExpr:
    if len(args) != 1:
        context.diagnostic(f"quasiquote expects exactly one argument, got {len(args)}", form)
        return QuoteExpr((), get_span(form))
    expanded = _expand_quasiquote_form(args[0])
    return _lower_form(expanded, scope, context, tail=tail)


def _expand_quasiquote_form(form: object, *, depth: int = 0) -> object:
    from qy.reader import DottedTuple as _DottedTuple

    if isinstance(form, tuple) and not isinstance(form, _DottedTuple) and form:
        op = form[0]
        if isinstance(op, Symbol) and op.name == "unquote":
            if depth == 0:
                return form[1] if len(form) == 2 else form
            return (
                Symbol("list"),
                Symbol("unquote"),
                _expand_quasiquote_form(form[1], depth=depth - 1),
            )
        if isinstance(op, Symbol) and op.name == "quasiquote":
            inner = _expand_quasiquote_form(form[1] if len(form) == 2 else form, depth=depth + 1)
            return (Symbol("list"), Symbol("quasiquote"), inner)
        return _build_quasiquote_tuple(form, depth=depth)
    return (Symbol("quote"), form)


def _build_quasiquote_tuple(form: tuple[object, ...], *, depth: int) -> object:
    from qy.reader import DottedTuple as _DottedTuple

    if not form:
        return (Symbol("quote"), ())
    head_form = form[0]
    tail_form = form[1:]
    if (
        isinstance(head_form, tuple)
        and not isinstance(head_form, _DottedTuple)
        and head_form
        and isinstance(head_form[0], Symbol)
        and head_form[0].name == "unquote-splicing"
        and depth == 0
    ):
        spliced = head_form[1] if len(head_form) == 2 else head_form
        rest = _build_quasiquote_tuple(tail_form, depth=depth)
        return (Symbol("append"), spliced, rest)
    head = _expand_quasiquote_form(head_form, depth=depth)
    rest = _build_quasiquote_tuple(tail_form, depth=depth)
    return (Symbol("cons"), head, rest)


def _lower_eval(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
) -> IRExpr:
    if len(args) != 1:
        context.diagnostic(f"eval expects exactly one argument, got {len(args)}", form)
        expression = LiteralExpr(None, "none", get_span(form))
    else:
        expression = _lower_form(args[0], scope, context)
    return RuntimeEvalExpr(expression, get_span(form))


def _lower_macro(
    form: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
) -> IRExpr:
    if len(form) < 4:
        context.diagnostic("macro expects a name, parameter list, and body", form)
        return MacroExpr(Symbol("<invalid>"), (), (), (), get_span(form))
    _, name, params, *body = form
    name = _ensure_symbol(name, "macro name", context)
    param_symbols = _parameter_symbols(params, "macro", context)
    macro_scope = _define_parameters(scope.child(), param_symbols, context)
    macro_scope = _define_local(
        macro_scope,
        Binding(Symbol("gensym"), "local", "operator", "pure"),
        context,
    )
    macro_scope = _define_local(
        macro_scope,
        Binding(Symbol("capture"), "local", "operator", "pure"),
        context,
    )
    lowered_body = _lower_body(tuple(body), macro_scope, context)
    return MacroExpr(name, param_symbols, lowered_body, tuple(body), get_span(form))


def _lower_cond(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
    *,
    tail: bool,
) -> IRExpr:
    clauses: list[CondClause] = []
    result_type: TypeName = "none"
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            context.diagnostic(f"cond clause must be a pair, got {clause!r}", clause)
            continue
        condition = _lower_form(clause[0], scope, context)
        result = _lower_form(clause[1], scope, context, tail=tail)
        result_type = _type_of(result)
        clauses.append(CondClause(condition, result))
    return CondExpr(tuple(clauses), get_span(form), result_type)


def _lower_let(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
    *,
    tail: bool,
) -> IRExpr:
    if len(args) < 2:
        context.diagnostic("let expects bindings and at least one body expression", form)
        return LetExpr((), (), get_span(form), "unknown")
    bindings_form, *body = args
    if not isinstance(bindings_form, tuple):
        context.diagnostic(f"let bindings must be a list, got {bindings_form!r}", bindings_form)
        return LetExpr(
            (), _lower_body(tuple(body), scope.child(), context, tail=tail), get_span(form)
        )

    local_scope = scope.child()
    bindings: list[LetBinding] = []
    for binding_form in bindings_form:
        if not isinstance(binding_form, tuple) or len(binding_form) != 2:
            context.diagnostic(f"let binding must be a pair, got {binding_form!r}", binding_form)
            continue
        name, value_form = binding_form
        name = _ensure_symbol(name, "let binding name", context)
        value = _lower_form(value_form, local_scope, context)
        bindings.append(LetBinding(name, value))
        local_scope = _define_local(
            local_scope,
            Binding(name, "local", _type_of(value)),
            context,
        )

    lowered_body = _lower_body(tuple(body), local_scope, context, tail=tail)
    return LetExpr(tuple(bindings), lowered_body, get_span(form), _body_type(lowered_body))


def _lower_lambda(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
) -> IRExpr:
    if len(args) < 2:
        context.diagnostic("lambda expects a parameter list and body", form)
        return LambdaExpr((), (), get_span(form))
    params, *body = args
    param_symbols = _parameter_symbols(params, "lambda", context)
    function_scope = _define_parameters(scope.child(), param_symbols, context)
    return LambdaExpr(
        param_symbols,
        _lower_body(tuple(body), function_scope, context, tail=True),
        get_span(form),
    )


def _lower_defun(
    form: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
) -> IRExpr:
    if len(form) < 4:
        context.diagnostic("defun expects a name, parameter list, and body", form)
        return DefineExpr(Symbol("<invalid>"), LambdaExpr((), (), get_span(form)), get_span(form))
    _, name, params, *body = form
    name = _ensure_symbol(name, "defun name", context)
    param_symbols = _parameter_symbols(params, "defun", context)
    function_scope = _define_local(
        scope.child(),
        Binding(name, "local", "function"),
        context,
    )
    function_scope = _define_parameters(function_scope, param_symbols, context)
    return DefineExpr(
        name,
        LambdaExpr(
            param_symbols,
            _lower_body(tuple(body), function_scope, context, tail=True),
            get_span(form),
        ),
        get_span(form),
    )


def _lower_defeffect(form: tuple[object, ...], context: LoweringContext) -> IRExpr:
    if len(form) < 2:
        context.diagnostic("defeffect expects an effect name", form)
        return DefineExpr(
            Symbol("<invalid>"),
            DefeffectExpr(Symbol("<invalid>"), True, get_span(form)),
            get_span(form),
        )
    _, name, *options = form
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
    )


def _lower_module(
    form: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
) -> IRExpr:
    if len(form) < 2:
        context.diagnostic("module expects a name and body", form)
        return ModuleExpr(Symbol("<invalid>"), (), (), get_span(form))
    _, name, *body = form
    name = _ensure_symbol(name, "module name", context)
    export_names: list[Symbol] = []
    module_scope = _predeclare_callable_definitions(tuple(body), scope.child(), context)
    lowered_body: list[IRExpr] = []
    for expression in body:
        if _is_special_form(expression, "exports"):
            if isinstance(expression, tuple):
                for item in expression[1:]:
                    if isinstance(item, Symbol):
                        export_names.append(item)
                    elif isinstance(item, tuple):
                        for sub in item:
                            if isinstance(sub, Symbol):
                                export_names.append(sub)
            continue
        lowered = _lower_form(expression, module_scope, context)
        lowered_body.append(lowered)
        module_scope = _scope_after_form(expression, lowered, module_scope, context)
    return ModuleExpr(name, tuple(lowered_body), tuple(export_names), get_span(form))


def _lower_from(form: tuple[object, ...], context: LoweringContext) -> IRExpr:
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

    for spec in specs:
        if spec.name not in source_module.exports and spec.name not in source_module.macro_exports:
            context.diagnostic(
                f"module {module_name.name!r} has no export {spec.name.name!r}",
                spec.name,
            )
    return FromImportExpr(module_name, specs, get_span(form))


def _lower_perform(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
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
    form: tuple[object, ...],
    *,
    tail: bool,
) -> IRExpr:
    if len(args) != 2:
        context.diagnostic(f"handle expects exactly two arguments, got {len(args)}", form)
        return HandleExpr(LiteralExpr(None, "none", get_span(form)), (), get_span(form))
    expression, handlers_form = args
    lowered_expression = _lower_form(expression, scope, context, tail=tail)
    handlers: list[EffectHandler] = []
    if not isinstance(handlers_form, tuple):
        context.diagnostic(f"handle clauses must be a list, got {handlers_form!r}", handlers_form)
        return HandleExpr(lowered_expression, (), get_span(form), _type_of(lowered_expression))
    result_type = _type_of(lowered_expression)
    for clause in handlers_form:
        if not isinstance(clause, tuple) or len(clause) < 3:
            context.diagnostic(
                f"handle clause must be (effect (arg k) body...), got {clause!r}", clause
            )
            continue
        effect, params, *body = clause
        effect = _ensure_symbol(effect, "handle effect name", context)
        if not _effect_is_declared(effect, scope, context):
            context.diagnostic(
                f"effect {effect.name!r} is not declared; add defeffect before handle", effect
            )
        param_symbols = _parameter_symbols(params, "handle", context)
        if len(param_symbols) != 2:
            context.diagnostic(f"handle parameters must be (arg k), got {params!r}", params)
            continue
        handler_scope = scope.child()
        handler_scope = _define_parameters(handler_scope, param_symbols, context)
        lowered_body = _lower_body(tuple(body), handler_scope, context, tail=tail)
        result_type = _body_type(lowered_body)
        handlers.append(EffectHandler(effect, param_symbols[0], param_symbols[1], lowered_body))
    return HandleExpr(lowered_expression, tuple(handlers), get_span(form), result_type)


def _lower_resume(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
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
    form: tuple[object, ...],
) -> IRExpr:
    if len(args) not in {1, 2}:
        context.diagnostic(f"assert expects one or two arguments, got {len(args)}", form)
    condition = (
        _lower_form(args[0], scope, context) if args else LiteralExpr(False, "bool", get_span(form))
    )
    message = _lower_form(args[1], scope, context, symbol_as_data=True) if len(args) > 1 else None
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
) -> Scope:
    del expr
    if not isinstance(form, tuple) or not form:
        return scope
    if len(form) >= 2 and form[0] == Symbol("defun") and isinstance(form[1], Symbol):
        if scope.has_local(form[1]):
            return scope
        return _define_local(scope, Binding(form[1], "local", "function"), context)
    if len(form) >= 2 and form[0] == Symbol("define") and isinstance(form[1], Symbol):
        return _define_local(scope, Binding(form[1], "local", "any"), context)
    if len(form) >= 2 and form[0] == Symbol("defeffect") and isinstance(form[1], Symbol):
        return _define_local(scope, Binding(form[1], "local", "effect"), context)
    if len(form) >= 2 and form[0] == Symbol("macro") and isinstance(form[1], Symbol):
        return _define_local(
            scope,
            Binding(form[1], "local", "operator", "meta", eager_arguments=False),
            context,
        )
    if len(form) >= 2 and form[0] == Symbol("module") and isinstance(form[1], Symbol):
        remember_source_module(form, context.env)
        return _define_local(scope, Binding(form[1], "local", "any"), context)
    if form[0] != Symbol("from"):
        return scope

    try:
        module_name, specs = parse_from_import(form)
        source_module = resolve_known_module(module_name.name, context.env)
    except (KeyError, ValueError):
        return scope

    next_scope = scope
    for spec in specs:
        if spec.name in source_module.exports:
            value = source_module.resolve(spec.name)
        elif spec.name in source_module.macro_exports:
            value = source_module.resolve_macro(spec.name)
        else:
            continue
        next_scope = _define_local(
            next_scope,
            Binding(
                spec.alias,
                "local",
                value_type(value),
                operator_kind_for_value(value),
                value_uses_eager_arguments(value),
                value,
            ),
            context,
        )
    return next_scope


def _predeclare_callable_definitions(
    body: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
) -> Scope:
    next_scope = scope
    for expression in body:
        if not isinstance(expression, tuple) or len(expression) < 2:
            continue
        if expression[0] != Symbol("defun"):
            continue
        name = expression[1]
        if isinstance(name, Symbol):
            next_scope = _define_local(next_scope, Binding(name, "local", "function"), context)
    return next_scope


def _define_local(scope: Scope, binding: Binding, context: LoweringContext) -> Scope:
    if scope.has_local(binding.symbol):
        context.diagnostic(
            f"symbol {binding.symbol.name!r} is already bound in this scope", binding.symbol
        )
    return scope.define(binding)


def _define_parameters(scope: Scope, params: tuple[Symbol, ...], context: LoweringContext) -> Scope:
    next_scope = scope
    for param in params:
        next_scope = _define_local(next_scope, Binding(param, "local", "any"), context)
    return next_scope


def _parameter_symbols(
    params: object,
    context_name: str,
    context: LoweringContext,
) -> tuple[Symbol, ...]:
    if not isinstance(params, tuple):
        context.diagnostic(f"{context_name} parameters must be a list, got {params!r}", params)
        return ()
    result: list[Symbol] = []
    for param in params:
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


def _infer_call_type(
    operator: object,
    args: tuple[IRExpr, ...],
    operator_expr: IRExpr,
    context: LoweringContext,
    form: tuple[object, ...],
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
    if operator_type not in {"operator", "function", "unknown"}:
        context.diagnostic(f"operator position is {operator_type}, not callable", form)
    return "any"


def _operator_signature(operator: IRExpr) -> OperatorSignature | None:
    if isinstance(operator, SymbolRefExpr):
        value = operator.binding.value
        return getattr(value, "signature", None)
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
    return isinstance(form, tuple) and len(form) > 0 and form[0] == Symbol(name)


def _lower_define(form: tuple[object, ...], scope: Scope, context: LoweringContext) -> IRExpr:
    if len(form) < 3:
        context.diagnostic("define expects a name and a value", form)
        return DefineExpr(
            Symbol("<invalid>"), LiteralExpr(None, "none", get_span(form)), get_span(form)
        )
    _, name_form, value_form = form[0], form[1], form[2]
    name = _ensure_symbol(name_form, "define name", context)
    value = _lower_form(value_form, scope, context)
    return DefineExpr(name, value, get_span(form))


def _lower_pipeline(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
    *,
    tail: bool = False,
) -> IRExpr:
    if not args:
        context.diagnostic("pipeline expects at least one expression", form)
        return LiteralExpr(None, "none", get_span(form))
    lowered = tuple(
        _lower_form(arg, scope, context, tail=tail and i == len(args) - 1)
        for i, arg in enumerate(args)
    )
    return PipelineExpr(lowered, get_span(form))


def _lower_parallel(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
) -> IRExpr:
    lowered = tuple(_lower_form(arg, scope, context) for arg in args)
    return ParallelExpr(lowered, get_span(form))


def _lower_all(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
) -> IRExpr:
    lowered = tuple(_lower_form(arg, scope, context) for arg in args)
    return AllExpr(lowered, get_span(form))


def _lower_race(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
) -> IRExpr:
    lowered = tuple(_lower_form(arg, scope, context) for arg in args)
    return RaceExpr(lowered, get_span(form))


def _lower_apply(
    args: tuple[object, ...],
    scope: Scope,
    context: LoweringContext,
    form: tuple[object, ...],
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
    form: tuple[object, ...],
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
