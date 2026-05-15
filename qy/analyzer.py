# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass

from qy.diagnostics import Diagnostic
from qy.evaluator import ControlOperator
from qy.evaluator import EffectDefinition
from qy.evaluator import EffectOperator
from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.evaluator import ScopeOperator
from qy.evaluator import UserFunction
from qy.evaluator import standard_environment
from qy.ir_vm._core import IRFunction
from qy.macro import MacroDefinition
from qy.operator_signature import OperatorSignature
from qy.operator_signature import format_arity_message
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import read
from qy.source_modules import remember_source_module
from qy.source_modules import resolve_known_module
from qy.stdlib.imports import parse_from_import
from qy.types import OperatorKind
from qy.types import TypeName
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyCons

__all__ = [
    "Analysis",
    "Diagnostic",
    "analyze",
    "analyze_source",
    "type_check_source",
]


@dataclass(frozen=True, slots=True)
class Analysis:
    forms: list[Form]
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


@dataclass(frozen=True, slots=True)
class _Binding:
    type_name: TypeName
    operator_kind: OperatorKind | None = None
    eager_arguments: bool = True
    signature: OperatorSignature | None = None


@dataclass(frozen=True, slots=True)
class _Scope:
    bindings: dict[Symbol, _Binding] | None = None

    def has_local(self, symbol: Symbol) -> bool:
        return self.bindings is not None and symbol in self.bindings

    def define(
        self,
        symbol: Symbol,
        type_name: TypeName = "any",
        *,
        operator_kind: OperatorKind | None = None,
        eager_arguments: bool = True,
        signature: OperatorSignature | None = None,
    ) -> _Scope:
        bindings = dict(self.bindings or {})
        bindings[symbol] = _Binding(type_name, operator_kind, eager_arguments, signature)
        return _Scope(bindings)

    def lookup(self, symbol: Symbol) -> _Binding | None:
        if self.bindings is None:
            return None
        return self.bindings.get(symbol)


def analyze_source(source: str, env: Environment | None = None) -> Analysis:
    try:
        forms = read(source)
    except ReaderSyntaxError as e:
        return Analysis(
            [],
            [Diagnostic(str(e), "error", line=e.line, column=e.column)],
        )
    return analyze(forms, env)


def analyze(forms: list[Form], env: Environment | None = None) -> Analysis:
    env = env or standard_environment()
    diagnostics: list[Diagnostic] = []
    scope = _predeclare_callable_definitions(tuple(forms), _Scope())
    for form in forms:
        _infer(form, env, scope, diagnostics)
        scope = _scope_after_form(form, env, scope)
    return Analysis(forms, diagnostics)


def type_check_source(source: str, env: Environment | None = None) -> list[Diagnostic]:
    return analyze_source(source, env).diagnostics


def _infer(
    form: object, env: Environment, scope: _Scope, diagnostics: list[Diagnostic]
) -> TypeName:
    if isinstance(form, Symbol):
        return _infer_symbol(form, env, scope, diagnostics)
    if not isinstance(form, tuple):
        return _literal_type(form)
    if isinstance(form, DottedTuple):
        diagnostics.append(Diagnostic("dotted form cannot be evaluated as a call"))
        return "unknown"
    if not form:
        return "tuple"

    operator = form[0]
    args = tuple(form[1:])

    if isinstance(operator, Symbol):
        match operator.name:
            case "quote":
                _check_arity(operator.name, args, diagnostics, exact=1)
                return "any"
            case "eval":
                _check_arity(operator.name, args, diagnostics, exact=1)
                for arg in args:
                    _infer(arg, env, scope, diagnostics)
                return "any"
            case "macro":
                return _infer_macro(form, env, scope, diagnostics)
            case "cond":
                return _infer_cond(args, env, scope, diagnostics)
            case "let":
                return _infer_let(args, env, scope, diagnostics)
            case "lambda":
                return _infer_lambda(args, env, scope, diagnostics)
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
                    _infer(arg, env, scope, diagnostics)
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

    operator_type = _infer(operator, env, scope, diagnostics)
    signature = _operator_signature(operator, env, scope)
    if signature is not None:
        return _infer_signature_call(
            operator,
            args,
            signature,
            env,
            scope,
            diagnostics,
        )
    if _operator_uses_eager_arguments(operator, env, scope) or operator_type in {
        "function",
        "unknown",
    }:
        for arg in args:
            _infer(arg, env, scope, diagnostics)
    if operator_type not in {"operator", "function", "unknown"}:
        diagnostics.append(Diagnostic(f"operator position is {operator_type}, not callable"))
    return "any"


def _infer_symbol(
    symbol: Symbol,
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if (binding := scope.lookup(symbol)) is not None:
        return binding.type_name
    try:
        return _value_type(env.resolve(symbol))
    except EvaluationError:
        diagnostics.append(Diagnostic(f"unresolved symbol {symbol.name!r}"))
        return "unknown"


def _literal_type(value: object) -> TypeName:
    if value is QY_NIL:
        return "nil"
    if value is QY_T:
        return "T"
    if isinstance(value, QyCons):
        return "chain"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "none"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, set):
        return "set"
    return "any"


def _value_type(value: object) -> TypeName:
    if isinstance(
        value, PureOperator | ScopeOperator | ControlOperator | EffectOperator | MetaOperator
    ):
        return "operator"
    if isinstance(value, UserFunction | IRFunction):
        return "function"
    if isinstance(value, MacroDefinition):
        return "operator"
    if isinstance(value, EffectDefinition):
        return "effect"
    return _literal_type(value)


def _operator_kind(operator: object, env: Environment, scope: _Scope) -> OperatorKind | None:
    if not isinstance(operator, Symbol):
        return None
    if (binding := scope.lookup(operator)) is not None:
        return binding.operator_kind
    try:
        return _operator_kind_for_value(env.resolve(operator))
    except EvaluationError:
        return None


def _operator_uses_eager_arguments(operator: object, env: Environment, scope: _Scope) -> bool:
    if not isinstance(operator, Symbol):
        return False
    if (binding := scope.lookup(operator)) is not None:
        return binding.operator_kind == "pure" and binding.eager_arguments
    try:
        return _value_uses_eager_arguments(env.resolve(operator))
    except EvaluationError:
        return False


def _operator_kind_for_value(value: object) -> OperatorKind | None:
    if isinstance(value, PureOperator):
        return "pure"
    if isinstance(value, ScopeOperator):
        return "scope"
    if isinstance(value, ControlOperator):
        return "control"
    if isinstance(value, EffectOperator):
        return "effect"
    if isinstance(value, MetaOperator):
        return "meta"
    if isinstance(value, MacroDefinition):
        return "meta"
    return None


def _value_uses_eager_arguments(value: object) -> bool:
    return isinstance(value, PureOperator) and value.argument_evaluator is None


def _value_signature(value: object) -> OperatorSignature | None:
    return getattr(value, "signature", None)


def _operator_signature(
    operator: object,
    env: Environment,
    scope: _Scope,
) -> OperatorSignature | None:
    if not isinstance(operator, Symbol):
        return None
    if (binding := scope.lookup(operator)) is not None:
        return binding.signature
    try:
        return _value_signature(env.resolve(operator))
    except EvaluationError:
        return None


def _infer_signature_call(
    operator: object,
    args: tuple[object, ...],
    signature: OperatorSignature,
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    name = operator.name if isinstance(operator, Symbol) else "call"
    if not signature.arity.accepts(len(args)):
        diagnostics.append(Diagnostic(_arity_message(name, signature, len(args))))
    for index, arg in enumerate(args):
        if not _signature_argument_is_eager(signature, index):
            continue
        arg_type = _infer(arg, env, scope, diagnostics)
        expected = _signature_argument_type(signature, index)
        if expected is not None and arg_type not in {expected, "unknown", "any"}:
            diagnostics.append(Diagnostic(f"{name} expects {expected} arguments, got {arg_type}"))
    return signature.return_type


def _signature_argument_is_eager(signature: OperatorSignature, index: int) -> bool:
    try:
        policy = signature.argument_policy[index]
    except IndexError:
        policy = "eager"
    return policy == "eager"


def _signature_argument_type(signature: OperatorSignature, index: int) -> TypeName | None:
    try:
        return signature.argument_types[index]
    except IndexError:
        return signature.rest_type


def _arity_message(name: str, signature: OperatorSignature, actual: int) -> str:
    return format_arity_message(name, signature, actual)


def _effect_is_declared(effect: Symbol, env: Environment, scope: _Scope) -> bool:
    if (binding := scope.lookup(effect)) is not None:
        return binding.type_name == "effect"
    try:
        return isinstance(env.resolve(effect), EffectDefinition)
    except EvaluationError:
        return False


def _infer_numeric_call(
    name: str,
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if name in {"-", "/"} and not args:
        diagnostics.append(Diagnostic(f"{name} expects at least one argument"))
    for arg in args:
        arg_type = _infer(arg, env, scope, diagnostics)
        if arg_type not in {"number", "unknown", "any"}:
            diagnostics.append(Diagnostic(f"{name} expects number arguments, got {arg_type}"))
    return "number"


def _infer_cond(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    result_type: TypeName = "none"
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            diagnostics.append(Diagnostic(f"cond clause must be a pair, got {clause!r}"))
            continue
        condition, result = clause
        _infer(condition, env, scope, diagnostics)
        result_type = _infer(result, env, scope, diagnostics)
    return result_type


def _infer_py(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not args:
        diagnostics.append(Diagnostic("py expects Python source and optional keyword arguments"))
        return "unknown"
    if len(args[1:]) % 2 != 0:
        diagnostics.append(Diagnostic("py keyword arguments must be :name value pairs"))
        return "any"

    for index in range(1, len(args), 2):
        keyword_name = args[index]
        if not isinstance(keyword_name, Symbol) or not keyword_name.name.startswith(":"):
            diagnostics.append(
                Diagnostic(f"py keyword name must be a :keyword symbol, got {keyword_name!r}")
            )
            continue
        _infer(args[index + 1], env, scope, diagnostics)
    return "any"


def _infer_assert(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) not in {1, 2}:
        diagnostics.append(Diagnostic(f"assert expects one or two arguments, got {len(args)}"))
        return "unknown"
    condition_type = _infer(args[0], env, scope, diagnostics)
    if len(args) == 2 and not isinstance(args[1], Symbol):
        _infer(args[1], env, scope, diagnostics)
    return condition_type


def _infer_data_args(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> None:
    for arg in args:
        _infer_data_arg(arg, env, scope, diagnostics)


def _infer_data_arg(
    arg: object,
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if isinstance(arg, Symbol):
        if (binding := scope.lookup(arg)) is not None:
            return binding.type_name
        try:
            return _value_type(env.resolve(arg))
        except EvaluationError:
            return "symbol"
    return _infer(arg, env, scope, diagnostics)


def _infer_from(
    form: tuple[object, ...], env: Environment, diagnostics: list[Diagnostic]
) -> TypeName:
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


def _infer_let(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) < 2:
        diagnostics.append(Diagnostic("let expects bindings and at least one body expression"))
        return "unknown"

    bindings, *body = args
    if not isinstance(bindings, tuple):
        diagnostics.append(Diagnostic(f"let bindings must be a list, got {bindings!r}"))
        return "unknown"

    local_scope = scope
    for binding in bindings:
        if not isinstance(binding, tuple) or len(binding) != 2:
            diagnostics.append(Diagnostic(f"let binding must be a pair, got {binding!r}"))
            continue
        name, expression = binding
        _infer(expression, env, local_scope, diagnostics)
        if isinstance(name, Symbol):
            local_scope = local_scope.define(name)
        else:
            diagnostics.append(Diagnostic(f"let binding name must be a symbol, got {name!r}"))

    return _infer_body(tuple(body), env, local_scope, diagnostics)


def _infer_lambda(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) < 2:
        diagnostics.append(Diagnostic("lambda expects a parameter list and body"))
        return "unknown"

    params, *body = args
    function_scope = _scope_with_parameters(params, scope, diagnostics, "lambda")
    _infer_body(tuple(body), env, function_scope, diagnostics)
    return "function"


def _infer_defun(
    form: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(form) < 4:
        diagnostics.append(Diagnostic("defun expects a name, parameter list, and body"))
        return "unknown"

    _, name, params, *body = form
    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"defun name must be a symbol, got {name!r}"))
    if not isinstance(params, tuple):
        diagnostics.append(Diagnostic(f"defun parameters must be a list, got {params!r}"))
        return "function"

    function_scope = scope
    if isinstance(name, Symbol):
        function_scope = function_scope.define(name, "function")
    for param in params:
        if isinstance(param, Symbol):
            function_scope = function_scope.define(param)
        else:
            diagnostics.append(Diagnostic(f"defun parameter must be a symbol, got {param!r}"))

    _infer_body(tuple(body), env, function_scope, diagnostics)
    return "function"


def _infer_defeffect(
    form: tuple[object, ...],
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(form) < 2:
        diagnostics.append(Diagnostic("defeffect expects an effect name"))
        return "unknown"
    _, name, *options = form
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
    form: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(form) < 4:
        diagnostics.append(Diagnostic("macro expects a name, parameter list, and body"))
        return "unknown"

    _, name, params, *body = form
    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"macro name must be a symbol, got {name!r}"))
    macro_scope = scope
    if isinstance(name, Symbol):
        macro_scope = macro_scope.define(
            name, "operator", operator_kind="meta", eager_arguments=False
        )
    macro_scope = _scope_with_parameters(params, macro_scope, diagnostics, "macro")
    macro_scope = macro_scope.define(Symbol("gensym"), "operator", operator_kind="pure")
    macro_scope = macro_scope.define(Symbol("capture"), "operator", operator_kind="pure")
    _infer_body(tuple(body), env, macro_scope, diagnostics)
    return "operator"


def _infer_perform(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    _check_arity("perform", args, diagnostics, exact=2)
    if len(args) < 2:
        return "unknown"
    effect, arg = args
    if not isinstance(effect, Symbol):
        diagnostics.append(Diagnostic(f"perform effect name must be a symbol, got {effect!r}"))
    elif not _effect_is_declared(effect, env, scope):
        diagnostics.append(
            Diagnostic(f"effect {effect.name!r} is not declared; add defeffect before perform")
        )
    _infer(arg, env, scope, diagnostics)
    return "any"


def _infer_handle(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    _check_arity("handle", args, diagnostics, exact=2)
    if len(args) < 2:
        return "unknown"
    expr, handler_form = args
    result_type = _infer(expr, env, scope, diagnostics)
    if not isinstance(handler_form, tuple):
        diagnostics.append(Diagnostic(f"handle clauses must be a list, got {handler_form!r}"))
        return result_type
    for clause in handler_form:
        if not isinstance(clause, tuple) or len(clause) < 3:
            diagnostics.append(
                Diagnostic(f"handle clause must be (effect (arg k) body...), got {clause!r}")
            )
            continue
        effect, params, *body = clause
        if isinstance(effect, Symbol):
            if not _effect_is_declared(effect, env, scope):
                diagnostics.append(
                    Diagnostic(
                        f"effect {effect.name!r} is not declared; add defeffect before handle"
                    )
                )
        else:
            diagnostics.append(Diagnostic(f"handle effect name must be a symbol, got {effect!r}"))
        handler_scope = _scope_with_parameters(params, scope, diagnostics, "handle")
        result_type = _infer_body(tuple(body), env, handler_scope, diagnostics)
    return result_type


def _infer_module(
    form: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(form) < 2:
        diagnostics.append(Diagnostic("module expects a name and body"))
        return "unknown"

    _, name, *body = form
    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"module name must be a symbol, got {name!r}"))

    module_scope = _predeclare_callable_definitions(tuple(body), scope)
    for expression in body:
        if _is_special_form(expression, "exports"):
            continue
        if _is_special_form(expression, "imports"):
            assert isinstance(expression, tuple)
            for import_form in expression[1:]:
                if isinstance(import_form, tuple):
                    _infer_from(import_form, env, diagnostics)
            continue
        _infer(expression, env, module_scope, diagnostics)
        module_scope = _scope_after_form(expression, env, module_scope)
    return "any"


def _infer_body(
    body: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not body:
        diagnostics.append(Diagnostic("body must contain at least one expression"))
        return "unknown"
    result_type: TypeName = "none"
    body_scope = _predeclare_callable_definitions(body, scope)
    for expression in body:
        result_type = _infer(expression, env, body_scope, diagnostics)
        body_scope = _scope_after_form(expression, env, body_scope)
    return result_type


def _scope_after_form(form: object, env: Environment, scope: _Scope) -> _Scope:
    if not isinstance(form, tuple) or not form:
        return scope
    if len(form) >= 2 and form[0] == Symbol("defun") and isinstance(form[1], Symbol):
        if scope.has_local(form[1]):
            return scope
        return scope.define(form[1], "function")
    if len(form) >= 2 and form[0] == Symbol("define") and isinstance(form[1], Symbol):
        if scope.has_local(form[1]):
            return scope
        return scope.define(form[1], "any")
    if len(form) >= 2 and form[0] == Symbol("defeffect") and isinstance(form[1], Symbol):
        if scope.has_local(form[1]):
            return scope
        return scope.define(form[1], "effect")
    if len(form) >= 2 and form[0] == Symbol("macro") and isinstance(form[1], Symbol):
        if scope.has_local(form[1]):
            return scope
        return scope.define(form[1], "operator", operator_kind="meta", eager_arguments=False)
    if len(form) >= 2 and form[0] == Symbol("module") and isinstance(form[1], Symbol):
        remember_source_module(form, env)
        if scope.has_local(form[1]):
            return scope
        return scope.define(form[1])
    if form[0] != Symbol("from"):
        return scope

    try:
        module_name, specs = parse_from_import(form)
        source_module = resolve_known_module(module_name.name, env)
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
        next_scope = next_scope.define(
            spec.alias,
            _value_type(value),
            operator_kind=_operator_kind_for_value(value),
            eager_arguments=_value_uses_eager_arguments(value),
            signature=_value_signature(value),
        )
    return next_scope


def _predeclare_callable_definitions(body: tuple[object, ...], scope: _Scope) -> _Scope:
    next_scope = scope
    for expression in body:
        if not isinstance(expression, tuple) or len(expression) < 2:
            continue
        if expression[0] != Symbol("defun"):
            continue
        name = expression[1]
        if isinstance(name, Symbol) and not next_scope.has_local(name):
            next_scope = next_scope.define(name, "function")
    return next_scope


def _check_arity(
    name: str,
    args: tuple[object, ...],
    diagnostics: list[Diagnostic],
    *,
    exact: int,
) -> None:
    if len(args) != exact:
        diagnostics.append(Diagnostic(f"{name} expects exactly {exact} arguments, got {len(args)}"))


def _scope_with_parameters(
    params: object,
    scope: _Scope,
    diagnostics: list[Diagnostic],
    context: str,
) -> _Scope:
    if not isinstance(params, tuple):
        diagnostics.append(Diagnostic(f"{context} parameters must be a list, got {params!r}"))
        return scope
    next_scope = scope
    for param in params:
        if isinstance(param, Symbol):
            next_scope = next_scope.define(param)
        else:
            diagnostics.append(Diagnostic(f"{context} parameter must be a symbol, got {param!r}"))
    return next_scope


def _is_special_form(form: object, name: str) -> bool:
    return isinstance(form, tuple) and len(form) > 0 and form[0] == Symbol(name)


def _infer_define(
    form: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(form) < 3:
        diagnostics.append(Diagnostic("define expects a name and a value"))
        return "unknown"
    _, name, value = form[0], form[1], form[2]
    if not isinstance(name, Symbol):
        diagnostics.append(Diagnostic(f"define name must be a symbol, got {name!r}"))
    elif scope.has_local(name):
        diagnostics.append(Diagnostic(f"symbol {name.name!r} is already bound in this scope"))
    _infer(value, env, scope, diagnostics)
    return "any"


def _infer_pipeline(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not args:
        diagnostics.append(Diagnostic("pipeline expects at least one expression"))
        return "unknown"
    result_type: TypeName = "none"
    for arg in args:
        result_type = _infer(arg, env, scope, diagnostics)
    return result_type


def _infer_parallel_or_all(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    for arg in args:
        _infer(arg, env, scope, diagnostics)
    return "any"


def _infer_apply(
    args: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if len(args) != 2:
        diagnostics.append(Diagnostic(f"apply expects exactly two arguments, got {len(args)}"))
        return "unknown"
    for arg in args:
        _infer(arg, env, scope, diagnostics)
    return "any"
