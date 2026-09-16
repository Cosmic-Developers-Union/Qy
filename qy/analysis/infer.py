# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy.ir.hir.predicates (public analyzer now lowers to HIR)
from __future__ import annotations

from typing import TYPE_CHECKING
from typing import cast

if TYPE_CHECKING:
    from collections.abc import Iterable

from qy.analysis.refs import arity_message
from qy.analysis.refs import effect_is_declared
from qy.analysis.refs import infer_symbol
from qy.analysis.refs import literal_type
from qy.analysis.refs import operator_signature
from qy.analysis.refs import operator_uses_eager_arguments
from qy.analysis.refs import signature_argument_is_eager
from qy.analysis.refs import signature_argument_type
from qy.analysis.scope import Scope
from qy.analysis.scope import binding_name
from qy.analysis.scope import predeclare_callable_definitions
from qy.analysis.scope import scope_after_form
from qy.analysis.scope import scope_with_parameters
from qy.core import TypeName
from qy.core.operator_signature import OperatorSignature
from qy.core.syntax import Symbol
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.diag import Diagnostic
from qy.import_.loader import resolve_known_module
from qy.import_.parse import parse_from_import
from qy.session.runtime_space import RuntimeSpace as Environment


def infer(form: object, env: Environment, scope: Scope, diagnostics: list[Diagnostic]) -> TypeName:
    if isinstance(form, Symbol):
        return infer_symbol(form, env, scope, diagnostics)
    if not is_chain(form):
        return literal_type(form)

    if is_nil(form):
        return "chain"

    operator = car(form)
    args_chain = cdr(form)
    try:
        args = (
            tuple(cast("Iterable[object]", args_chain))
            if is_chain(args_chain)
            else ()
            if is_nil(args_chain)
            else (args_chain,)
        )
    except ValueError:
        diagnostics.append(Diagnostic("improper list cannot be evaluated as a call"))
        return "unknown"

    if isinstance(operator, Symbol):
        match operator.name:
            case "quote":
                _check_arity(operator.name, args, diagnostics, exact=1)
                return "any"
            case "eval":
                _check_arity(operator.name, args, diagnostics, exact=1)
                for arg in args:
                    infer(arg, env, scope, diagnostics)
                return "any"
            case "macro":
                return _infer_macro(form, env, scope, diagnostics)
            case "cond":
                return _infer_cond(args, env, scope, diagnostics)
            case "let":
                return _infer_let(args, env, scope, diagnostics)
            case "lambda":
                return _infer_lambda(args, env, scope, diagnostics)
            case "component":
                return _infer_component(args, env, scope, diagnostics)
            case "defun":
                return _infer_defun(form, env, scope, diagnostics)
            case "defeffect":
                return _infer_defeffect(form, diagnostics)
            case "module":
                return _infer_module(form, env, scope, diagnostics)
            case "from":
                return _infer_from(form, env, diagnostics)
            case "perform":
                return _infer_perform(args, env, scope, diagnostics)
            case "handle":
                return _infer_handle(args, env, scope, diagnostics)
            case "resume":
                _check_arity(operator.name, args, diagnostics, exact=2)
                for arg in args:
                    infer(arg, env, scope, diagnostics)
                return "any"
            case "assert":
                return _infer_assert(args, env, scope, diagnostics)
            case "define":
                return _infer_define(form, env, scope, diagnostics)
            case "pipeline":
                return _infer_pipeline(args, env, scope, diagnostics)
            case "parallel":
                return _infer_parallel_or_all(args, env, scope, diagnostics)
            case "all":
                return _infer_parallel_or_all(args, env, scope, diagnostics)
            case "race":
                return _infer_parallel_or_all(args, env, scope, diagnostics)
            case "apply":
                return _infer_apply(args, env, scope, diagnostics)

    operator_type = infer(operator, env, scope, diagnostics)
    sig = operator_signature(operator, env, scope) if isinstance(operator, Symbol) else None
    if sig is not None:
        return _infer_signature_call(operator, args, sig, env, scope, diagnostics)
    eager = (
        operator_uses_eager_arguments(operator, env, scope)
        if isinstance(operator, Symbol)
        else False
    )
    if eager or operator_type in {"function", "unknown"}:
        for arg in args:
            infer(arg, env, scope, diagnostics)
    if operator_type not in {"operator", "function", "unknown", "any"}:
        diagnostics.append(Diagnostic(f"operator position is {operator_type}, not callable"))
    return "any"


def _infer_signature_call(
    operator: object,
    args: tuple[object, ...],
    sig: OperatorSignature,
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    name = operator.name if isinstance(operator, Symbol) else "call"
    if not sig.arity.accepts(len(args)):
        diagnostics.append(Diagnostic(arity_message(name, sig, len(args))))
    for index, arg in enumerate(args):
        if not signature_argument_is_eager(sig, index):
            continue
        arg_type = infer(arg, env, scope, diagnostics)
        expected = signature_argument_type(sig, index)
        if expected is not None and arg_type not in {expected, "unknown", "any"}:
            diagnostics.append(Diagnostic(f"{name} expects {expected} arguments, got {arg_type}"))
    return sig.return_type


def _infer_cond(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    result_type: TypeName = "none"
    for clause in args:
        if not is_chain(clause):
            diagnostics.append(Diagnostic(f"cond clause must be a pair, got {clause!r}"))
            continue
        try:
            clause_list = list(cast("Iterable[object]", clause))
            if len(clause_list) != 2:
                diagnostics.append(Diagnostic(f"cond clause must be a pair, got {clause!r}"))
                continue
            condition, result = clause_list
        except ValueError:
            diagnostics.append(Diagnostic(f"cond clause must be a proper list, got {clause!r}"))
            continue
        infer(condition, env, scope, diagnostics)
        result_type = infer(result, env, scope, diagnostics)
    return result_type


def _infer_let(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) < 2:
        diagnostics.append(Diagnostic("let expects bindings and at least one body expression"))
        return "unknown"

    bindings, *body = args
    if not is_chain(bindings) and not is_nil(bindings):
        diagnostics.append(Diagnostic(f"let bindings must be a list, got {bindings!r}"))
        return "unknown"

    local_scope = scope
    try:
        for binding in cast("Iterable[object]", bindings) if is_chain(bindings) else []:
            if not is_chain(binding):
                diagnostics.append(Diagnostic(f"let binding must be a pair, got {binding!r}"))
                continue
            try:
                binding_list = list(cast("Iterable[object]", binding))
                if len(binding_list) != 2:
                    diagnostics.append(Diagnostic(f"let binding must be a pair, got {binding!r}"))
                    continue
                name, expression = binding_list
            except ValueError:
                diagnostics.append(
                    Diagnostic(f"let binding must be a proper list, got {binding!r}")
                )
                continue
            infer(expression, env, local_scope, diagnostics)
            if isinstance(name, Symbol):
                local_scope = local_scope.define(name)
            else:
                diagnostics.append(Diagnostic(f"let binding name must be a symbol, got {name!r}"))
    except ValueError:
        diagnostics.append(Diagnostic(f"let bindings must be a proper list, got {bindings!r}"))
        return "unknown"

    return _infer_body(tuple(body), env, local_scope, diagnostics)


def _infer_lambda(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) < 2:
        diagnostics.append(Diagnostic("lambda expects a parameter list and body"))
        return "unknown"

    params, *body = args
    function_scope = scope_with_parameters(params, scope, diagnostics, "lambda")
    _infer_body(tuple(body), env, function_scope, diagnostics)
    return "function"


def _infer_component(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) < 2:
        diagnostics.append(Diagnostic("component expects at least 2 operators"))
        return "unknown"

    # 推断所有算子参数的类型
    for arg in args:
        infer(arg, env, scope, diagnostics)

    # component 返回一个函数
    return "function"


def _infer_defun(
    form: object,
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not is_chain(form):
        diagnostics.append(Diagnostic("defun form must be a list"))
        return "unknown"

    try:
        form_list = list(cast("Iterable[object]", form))
        if len(form_list) < 4:
            diagnostics.append(Diagnostic("defun expects a name, parameter list, and body"))
            return "unknown"

        _, name, params, *body = form_list
    except ValueError:
        diagnostics.append(Diagnostic("defun form must be a proper list"))
        return "unknown"

    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"defun name must be a symbol, got {name!r}"))
    if not (is_chain(params) or isinstance(params, tuple) or is_nil(params)):
        diagnostics.append(Diagnostic(f"defun parameters must be a list, got {params!r}"))
        return "function"

    function_scope = scope
    if isinstance(name, Symbol):
        function_scope = function_scope.define(name, "function")

    try:
        params_list = (
            chain_to_list(params)
            if is_chain(params)
            else (list(params) if isinstance(params, tuple) else [])
        )
        for param in params_list:
            if isinstance(param, Symbol):
                function_scope = function_scope.define(param)
            else:
                diagnostics.append(Diagnostic(f"defun parameter must be a symbol, got {param!r}"))
    except ValueError:
        diagnostics.append(Diagnostic(f"defun parameters must be a proper list, got {params!r}"))

    _infer_body(tuple(body), env, function_scope, diagnostics)
    return "function"


def _infer_defeffect(
    form: object,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not is_chain(form):
        diagnostics.append(Diagnostic("defeffect form must be a list"))
        return "unknown"

    try:
        form_list = list(cast("Iterable[object]", form))
        if len(form_list) < 2:
            diagnostics.append(Diagnostic("defeffect expects an effect name"))
            return "unknown"
        _, name, *options = form_list
    except ValueError:
        diagnostics.append(Diagnostic("defeffect form must be a proper list"))
        return "unknown"

    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"defeffect name must be a symbol, got {name!r}"))
    if options and (
        len(options) != 2
        or options[0] != Symbol(":resumable")
        or options[1] not in {Symbol("true"), Symbol("false")}
    ):
        diagnostics.append(Diagnostic("defeffect options must be empty or :resumable true|false"))
    return "effect"


def _infer_macro(
    form: object,
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not is_chain(form):
        diagnostics.append(Diagnostic("macro form must be a list"))
        return "unknown"

    try:
        form_list = list(cast("Iterable[object]", form))
        if len(form_list) < 4:
            diagnostics.append(Diagnostic("macro expects a name, parameter list, and body"))
            return "unknown"

        _, name, params, *body = form_list
    except ValueError:
        diagnostics.append(Diagnostic("macro form must be a proper list"))
        return "unknown"

    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"macro name must be a symbol, got {name!r}"))
    macro_scope = scope
    if isinstance(name, Symbol):
        macro_scope = macro_scope.define(
            name, "operator", operator_kind="meta", eager_arguments=False
        )
    macro_scope = scope_with_parameters(params, macro_scope, diagnostics, "macro")
    macro_scope = macro_scope.define(Symbol("gensym"), "operator", operator_kind="pure")
    macro_scope = macro_scope.define(Symbol("capture"), "operator", operator_kind="pure")
    _infer_body(tuple(body), env, macro_scope, diagnostics)
    return "operator"


def _infer_perform(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    _check_arity("perform", args, diagnostics, exact=2)
    if len(args) < 2:
        return "unknown"
    effect, arg = args
    if not isinstance(effect, Symbol):
        diagnostics.append(Diagnostic(f"perform effect name must be a symbol, got {effect!r}"))
    elif not effect_is_declared(effect, env, scope):
        diagnostics.append(
            Diagnostic(f"effect {effect.name!r} is not declared; add defeffect before perform")
        )
    infer(arg, env, scope, diagnostics)
    return "any"


def _is_on_form(form: object) -> bool:
    """是否为 ``(on effect (args) k body...)`` handler 形式。."""
    if not is_chain(form):
        return False
    return car(form) == Symbol("on")


def _define_handler_parameters(scope: Scope, symbols: tuple[Symbol, ...]) -> Scope:
    next_scope = scope
    for symbol in symbols:
        next_scope = next_scope.define(symbol)
    return next_scope


def _infer_handle(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    """推断 handle。.

    与 ``hir.lower`` 保持同一套 clause 语法，支持两种等价写法：

    - 标准格式：``(handle expression ((effect (arg k) body...) ...))``
    - on 格式：``(handle (on effect (arg k) body...) expression)``

    on 格式的 effect 由 lowering 自动声明，因此 analyzer 不能对它报
    "not declared"；标准格式仍要求先 ``defeffect``。
    """
    _check_arity("handle", args, diagnostics, exact=2)
    if len(args) < 2:
        return "unknown"
    first, second = args
    if _is_on_form(first):
        expression, handlers_form = second, first
    else:
        expression, handlers_form = first, second

    result_type = infer(expression, env, scope, diagnostics)

    if _is_on_form(handlers_form):
        handlers_list: list[object] = [handlers_form]
    elif is_nil(handlers_form):
        handlers_list = []
    elif is_chain(handlers_form) or isinstance(handlers_form, tuple):
        try:
            handlers_list = list(cast("Iterable[object]", handlers_form))
        except ValueError:
            diagnostics.append(
                Diagnostic(f"handle clauses must be a proper list, got {handlers_form!r}")
            )
            return result_type
    else:
        diagnostics.append(Diagnostic(f"handle clauses must be a list, got {handlers_form!r}"))
        return result_type

    for clause in handlers_list:
        if not is_chain(clause):
            diagnostics.append(
                Diagnostic(f"handle clause must be (effect (arg k) body...), got {clause!r}")
            )
            continue
        try:
            clause_list = list(cast("Iterable[object]", clause))
        except ValueError:
            diagnostics.append(Diagnostic(f"handle clause must be a proper list, got {clause!r}"))
            continue

        is_on_clause = (
            len(clause_list) >= 4
            and isinstance(clause_list[0], Symbol)
            and clause_list[0].name == "on"
        )
        if is_on_clause:
            _, effect, params, *body = clause_list
        elif len(clause_list) >= 3:
            effect, params, *body = clause_list
        else:
            diagnostics.append(
                Diagnostic(f"handle clause must be (effect (arg k) body...), got {clause!r}")
            )
            continue

        if not isinstance(effect, Symbol):
            diagnostics.append(Diagnostic(f"handle effect name must be a symbol, got {effect!r}"))
            continue
        # on 格式的 effect 由 lowering 自动声明；标准格式要求已声明。
        if not is_on_clause and not effect_is_declared(effect, env, scope):
            diagnostics.append(
                Diagnostic(f"effect {effect.name!r} is not declared; add defeffect before handle")
            )

        if is_on_clause and is_nil(params):
            param_symbols: tuple[Symbol, ...] = (Symbol("_v"), Symbol("k"))
        elif is_chain(params) or isinstance(params, tuple) or is_nil(params):
            params_list = (
                chain_to_list(params)
                if is_chain(params)
                else (list(params) if isinstance(params, tuple) else [])
            )
            param_symbols = tuple(param for param in params_list if isinstance(param, Symbol))
            for param in params_list:
                if not isinstance(param, Symbol):
                    diagnostics.append(
                        Diagnostic(f"handle parameter must be a symbol, got {param!r}")
                    )
        else:
            diagnostics.append(Diagnostic(f"handle parameters must be a list, got {params!r}"))
            continue
        # on 格式支持 (on effect (value) k body...)：k 独立 symbol 跟在参数列表后。
        if is_on_clause and len(param_symbols) == 1 and body and isinstance(body[0], Symbol):
            param_symbols = (param_symbols[0], body[0])
            body = body[1:]
        if len(param_symbols) != 2:
            diagnostics.append(Diagnostic(f"handle parameters must be (arg k), got {params!r}"))
            continue
        handler_scope = _define_handler_parameters(scope, param_symbols)
        result_type = _infer_body(tuple(body), env, handler_scope, diagnostics)

    return result_type


def _infer_module(
    form: object,
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not is_chain(form):
        diagnostics.append(Diagnostic("module form must be a list"))
        return "unknown"

    try:
        form_list = list(cast("Iterable[object]", form))
        if len(form_list) < 2:
            diagnostics.append(Diagnostic("module expects a name and body"))
            return "unknown"

        _, name, *body = form_list
    except ValueError:
        diagnostics.append(Diagnostic("module form must be a proper list"))
        return "unknown"

    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"module name must be a symbol, got {name!r}"))

    module_scope = predeclare_callable_definitions(tuple(body), scope)
    for expression in body:
        if _is_special_form(expression, "exports"):
            continue
        infer(expression, env, module_scope, diagnostics)
        module_scope = scope_after_form(expression, env, module_scope)
    return "any"


def _infer_from(form: object, env: Environment, diagnostics: list[Diagnostic]) -> TypeName:
    try:
        module_name, specs = parse_from_import(form)
    except ValueError as e:
        diagnostics.append(Diagnostic(str(e)))
        return "none"

    try:
        source_module = resolve_known_module(module_name.name, env)
    except KeyError as e:
        diagnostics.append(Diagnostic(str(e)))
        return "none"

    for spec in specs:
        if spec.name not in source_module.exports and spec.name not in source_module.macro_exports:
            diagnostics.append(
                Diagnostic(f"module {module_name.name!r} has no export {spec.name.name!r}")
            )
    return "none"


def _infer_body(
    body: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not body:
        diagnostics.append(Diagnostic("body must contain at least one expression"))
        return "unknown"
    result_type: TypeName = "none"
    body_scope = predeclare_callable_definitions(body, scope)
    for expression in body:
        result_type = infer(expression, env, body_scope, diagnostics)
        body_scope = scope_after_form(expression, env, body_scope)
    return result_type


def _infer_define(
    form: object,
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if is_chain(form):
        try:
            items = chain_to_list(form)
        except ValueError:
            diagnostics.append(Diagnostic("improper list in define"))
            return "unknown"
    else:
        items = list(cast("Iterable[object]", form))

    if len(items) < 3:
        diagnostics.append(Diagnostic("define expects a name and a value"))
        return "unknown"
    _, raw_name, value = items[0], items[1], items[2]
    name = binding_name(raw_name)
    if name is None:
        diagnostics.append(Diagnostic(f"define name must be a symbol, got {raw_name!r}"))
    elif scope.has_local(name):
        diagnostics.append(Diagnostic(f"symbol {name.name!r} is already bound in this scope"))
    infer(value, env, scope, diagnostics)
    return "any"


def _infer_assert(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) not in {1, 2}:
        diagnostics.append(Diagnostic(f"assert expects one or two arguments, got {len(args)}"))
        return "unknown"
    condition_type = infer(args[0], env, scope, diagnostics)
    if len(args) == 2 and not isinstance(args[1], Symbol):
        infer(args[1], env, scope, diagnostics)
    return condition_type


def _infer_pipeline(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not args:
        diagnostics.append(Diagnostic("pipeline expects at least one expression"))
        return "unknown"
    result_type: TypeName = "none"
    for arg in args:
        result_type = infer(arg, env, scope, diagnostics)
    return result_type


def _infer_parallel_or_all(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    for arg in args:
        infer(arg, env, scope, diagnostics)
    return "any"


def _infer_apply(
    args: tuple[object, ...],
    env: Environment,
    scope: Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) != 2:
        diagnostics.append(Diagnostic(f"apply expects exactly two arguments, got {len(args)}"))
        return "unknown"
    for arg in args:
        infer(arg, env, scope, diagnostics)
    return "any"


def _check_arity(
    name: str,
    args: tuple[object, ...],
    diagnostics: list[Diagnostic],
    *,
    exact: int,
) -> None:
    if len(args) != exact:
        diagnostics.append(Diagnostic(f"{name} expects exactly {exact} arguments, got {len(args)}"))


def _is_special_form(form: object, name: str) -> bool:
    if is_chain(form):
        items = chain_to_list(form)
        return len(items) > 0 and items[0] == Symbol(name)
    return isinstance(form, tuple) and len(form) > 0 and form[0] == Symbol(name)
