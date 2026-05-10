# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qy.evaluator import Environment
from qy.evaluator import EvaluationError
from qy.evaluator import EvaluationOperator
from qy.evaluator import PureOperator
from qy.evaluator import SyntaxOperator
from qy.evaluator import UserFunction
from qy.evaluator import standard_environment
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import read

__all__ = [
    "Analysis",
    "Diagnostic",
    "analyze",
    "analyze_source",
    "type_check_source",
]

Severity = Literal["error", "warning", "hint"]
TypeName = Literal[
    "any", "bool", "function", "nil", "number", "operator", "symbol", "tuple", "unknown"
]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    message: str
    severity: Severity = "error"
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class Analysis:
    forms: list[Form]
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


@dataclass(frozen=True, slots=True)
class _Scope:
    bindings: dict[Symbol, TypeName] | None = None

    def define(self, symbol: Symbol, type_name: TypeName = "any") -> _Scope:
        bindings = dict(self.bindings or {})
        bindings[symbol] = type_name
        return _Scope(bindings)

    def lookup(self, symbol: Symbol) -> TypeName | None:
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
    scope = _Scope()
    for form in forms:
        _infer(form, env, scope, diagnostics)
        if (
            isinstance(form, tuple)
            and len(form) >= 2
            and form[0] == Symbol("defun")
            and isinstance(form[1], Symbol)
        ):
            scope = scope.define(form[1], "function")
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
    if not form:
        return "tuple"

    operator = form[0]
    args = tuple(form[1:])

    if isinstance(operator, Symbol):
        match operator.name:
            case "quote":
                _check_arity(operator.name, args, diagnostics, exact=1)
                return "any"
            case "cond":
                return _infer_cond(args, env, scope, diagnostics)
            case "let":
                return _infer_let(args, env, scope, diagnostics)
            case "defun":
                return _infer_defun(form, env, scope, diagnostics)
            case "+" | "-" | "*" | "/":
                return _infer_numeric_call(operator.name, args, env, scope, diagnostics)
            case "atom" | "eq":
                for arg in args:
                    _infer(arg, env, scope, diagnostics)
                return "bool"
            case "car":
                _check_arity(operator.name, args, diagnostics, exact=1)
                for arg in args:
                    _infer(arg, env, scope, diagnostics)
                return "any"
            case "cdr" | "cons":
                for arg in args:
                    _infer(arg, env, scope, diagnostics)
                return "tuple"

    operator_type = _infer(operator, env, scope, diagnostics)
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
    if (type_name := scope.lookup(symbol)) is not None:
        return type_name
    try:
        return _value_type(env.resolve(symbol))
    except EvaluationError:
        diagnostics.append(Diagnostic(f"unresolved symbol {symbol.name!r}"))
        return "unknown"


def _literal_type(value: object) -> TypeName:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "nil"
    if isinstance(value, tuple):
        return "tuple"
    return "any"


def _value_type(value: object) -> TypeName:
    if isinstance(value, PureOperator | EvaluationOperator | SyntaxOperator):
        return "operator"
    if isinstance(value, UserFunction):
        return "function"
    return _literal_type(value)


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
    result_type: TypeName = "nil"
    for clause in args:
        if not isinstance(clause, tuple) or len(clause) != 2:
            diagnostics.append(Diagnostic(f"cond clause must be a pair, got {clause!r}"))
            continue
        condition, result = clause
        _infer(condition, env, scope, diagnostics)
        result_type = _infer(result, env, scope, diagnostics)
    return result_type


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
    for param in params:
        if isinstance(param, Symbol):
            function_scope = function_scope.define(param)
        else:
            diagnostics.append(Diagnostic(f"defun parameter must be a symbol, got {param!r}"))

    _infer_body(tuple(body), env, function_scope, diagnostics)
    return "function"


def _infer_body(
    body: tuple[object, ...],
    env: Environment,
    scope: _Scope,
    diagnostics: list[Diagnostic],
) -> TypeName:
    if not body:
        diagnostics.append(Diagnostic("body must contain at least one expression"))
        return "unknown"
    result_type: TypeName = "nil"
    for expression in body:
        result_type = _infer(expression, env, scope, diagnostics)
    return result_type


def _check_arity(
    name: str,
    args: tuple[object, ...],
    diagnostics: list[Diagnostic],
    *,
    exact: int,
) -> None:
    if len(args) != exact:
        diagnostics.append(Diagnostic(f"{name} expects exactly {exact} arguments, got {len(args)}"))
