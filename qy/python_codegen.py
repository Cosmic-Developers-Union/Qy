# coding: utf-8
"""Python code generator for QyLang HIR.

Translates a ProgramIR into Python source text.  The pure-functional
subset (literals, arithmetic, let, cond, defun, lambda) maps cleanly;
effects emit a ``raise NotImplementedError`` placeholder.
"""

from __future__ import annotations

from qy.ir import AllExpr
from qy.ir import ApplyExpr
from qy.ir import AssertExpr
from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefeffectExpr
from qy.ir import DefineExpr
from qy.ir import DefunExpr
from qy.ir import HandleExpr
from qy.ir import IRExpr
from qy.ir import LambdaExpr
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
from qy.reader import DottedTuple
from qy.reader import Symbol

__all__ = ["CodegenError", "codegen_python"]

_INFIX_OPS: dict[str, str] = {
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "//": "//",
    "%": "%",
    "**": "**",
    "<": "<",
    ">": ">",
    "<=": "<=",
    ">=": ">=",
    "eq": "==",
    "and": "and",
    "or": "or",
}

_UNARY_OPS: dict[str, str] = {
    "not": "not ",
    "-": "-",
}

_LITERAL_SYMBOLS: dict[str, str] = {
    "true": "True",
    "false": "False",
    "nil": "None",
    "none": "None",
}


class CodegenError(Exception):
    pass


def codegen_python(program: ProgramIR) -> str:
    lines: list[str] = []
    for expr in program.body:
        lines.extend(_toplevel(expr))
    return "\n".join(lines) + "\n" if lines else ""


def _toplevel(expr: IRExpr) -> list[str]:
    if isinstance(expr, DefunExpr):
        return _defun(expr)
    if isinstance(expr, DefineExpr):
        if isinstance(expr.value, LambdaExpr):
            return _define_lambda(expr.name, expr.value)
        if isinstance(expr.value, DefeffectExpr):
            return [f"# effect {expr.name.name} (resumable={expr.value.resumable})"]
        value_code = _expr(expr.value)
        return [f"{_mangle(expr.name.name)} = {value_code}"]
    if isinstance(expr, PipelineExpr):
        if not expr.body:
            return ["_result = None"]
        lines: list[str] = []
        for e in expr.body[:-1]:
            lines.append(f"_result = {_expr(e)}")
        lines.append(f"_result = {_expr(expr.body[-1])}")
        return lines
    if isinstance(expr, MacroExpr):
        return [f"# macro {_mangle(expr.name.name)}"]
    if isinstance(expr, DefeffectExpr):
        return [f"# effect {expr.name.name} (resumable={expr.resumable})"]
    code = _expr(expr)
    return [f"_result = {code}"]


def _defun(expr: DefunExpr, indent: int = 0) -> list[str]:
    prefix = "    " * indent
    params = ", ".join(_mangle(p.name) for p in expr.params)
    lines = [f"{prefix}def {_mangle(expr.name.name)}({params}):"]
    body_lines = _body(expr.body, indent + 1)
    lines.extend(body_lines)
    return lines


def _define_lambda(name: Symbol, value: LambdaExpr, indent: int = 0) -> list[str]:
    prefix = "    " * indent
    params = ", ".join(_mangle(p.name) for p in value.params)
    lines = [f"{prefix}def {_mangle(name.name)}({params}):"]
    lines.extend(_body(value.body, indent + 1))
    return lines


def _body(body: tuple[IRExpr, ...], indent: int) -> list[str]:
    prefix = "    " * indent
    if not body:
        return [f"{prefix}pass"]
    lines: list[str] = []
    for expr in body[:-1]:
        if isinstance(expr, DefunExpr):
            lines.extend(_defun(expr, indent))
        elif isinstance(expr, MacroExpr):
            lines.append(f"{prefix}# macro {_mangle(expr.name.name)}")
        else:
            lines.append(f"{prefix}{_expr(expr)}")
    last = body[-1]
    if isinstance(last, DefunExpr):
        lines.extend(_defun(last, indent))
        lines.append(f"{prefix}return {_mangle(last.name.name)}")
    else:
        lines.append(f"{prefix}return {_expr(last)}")
    return lines


def _expr(expr: IRExpr) -> str:
    if isinstance(expr, LiteralExpr):
        return _literal(expr)
    if isinstance(expr, SymbolRefExpr):
        name = expr.symbol.name
        if name in _LITERAL_SYMBOLS:
            return _LITERAL_SYMBOLS[name]
        return _mangle(name)
    if isinstance(expr, UnresolvedSymbolExpr):
        name = expr.symbol.name
        if name in _LITERAL_SYMBOLS:
            return _LITERAL_SYMBOLS[name]
        return _mangle(name)
    if isinstance(expr, QuoteExpr):
        return _quote(expr.form)
    if isinstance(expr, CondExpr):
        return _cond(expr)
    if isinstance(expr, LetExpr):
        return _let(expr)
    if isinstance(expr, LambdaExpr):
        return _lambda(expr)
    if isinstance(expr, CallExpr):
        return _call(expr)
    if isinstance(expr, AssertExpr):
        return _assert(expr)
    if isinstance(expr, PerformExpr):
        return f"_effect_perform({_mangle(expr.effect.name)!r})"
    if isinstance(expr, HandleExpr):
        return "_effect_handle(...)"
    if isinstance(expr, ResumeExpr):
        return f"_effect_resume({_expr(expr.continuation)}, {_expr(expr.value)})"
    if isinstance(expr, RuntimeEvalExpr):
        return f"_runtime_eval({_expr(expr.expression)})"
    if isinstance(expr, (DefeffectExpr, MacroExpr, ModuleExpr)):
        return "None"
    if isinstance(expr, DefunExpr):
        return _mangle(expr.name.name)
    if isinstance(expr, DefineExpr):
        return f"({_mangle(expr.name.name)} := {_expr(expr.value)})"
    if isinstance(expr, PipelineExpr):
        if not expr.body:
            return "None"
        parts = [_expr(e) for e in expr.body]
        return f"({', '.join(parts)})[-1]" if len(parts) > 1 else parts[0]
    if isinstance(expr, (ParallelExpr, AllExpr, RaceExpr, ApplyExpr)):
        raise CodegenError(f"unsupported IR expression: {type(expr).__name__}")
    raise CodegenError(f"unsupported IR expression: {type(expr).__name__}")


def _literal(expr: LiteralExpr) -> str:
    value = expr.value
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, Symbol):
        name = value.name
        if name in _LITERAL_SYMBOLS:
            return _LITERAL_SYMBOLS[name]
        return repr(name)
    return repr(value)


def _quote(form: object) -> str:
    if isinstance(form, Symbol):
        return repr(form.name)
    if isinstance(form, DottedTuple):
        items = ", ".join(_quote(item) for item in form)
        tail = _quote(form.tail)
        return f"({items}, {tail})" if items else tail
    if isinstance(form, tuple):
        items = ", ".join(_quote(item) for item in form)
        return f"({items},)" if len(form) == 1 else f"({items})" if items else "()"
    if isinstance(form, bool):
        return "True" if form else "False"
    return repr(form)


def _cond(expr: CondExpr) -> str:
    if not expr.clauses:
        return "None"
    result = "None"
    for clause in reversed(expr.clauses):
        cond_code = _expr(clause.condition)
        then_code = _expr(clause.result)
        if cond_code in ("True", "true"):
            result = then_code
        else:
            result = f"({then_code} if {cond_code} else {result})"
    return result


def _let(expr: LetExpr) -> str:
    if not expr.bindings:
        return _expr(expr.body[-1]) if expr.body else "None"
    params = ", ".join(_mangle(b.symbol.name) for b in expr.bindings)
    values = ", ".join(_expr(b.value) for b in expr.bindings)
    body_code = _let_body(expr.body)
    if len(expr.bindings) == 1:
        return f"(lambda {params}: {body_code})({values})"
    return f"(lambda {params}: {body_code})({values})"


def _let_body(body: tuple[IRExpr, ...]) -> str:
    if not body:
        return "None"
    if len(body) == 1:
        return _expr(body[0])
    parts = [_expr(e) for e in body]
    return f"({', '.join(parts)})[-1]"


def _lambda(expr: LambdaExpr) -> str:
    params = ", ".join(_mangle(p.name) for p in expr.params)
    body_code = _let_body(expr.body)
    return f"(lambda {params}: {body_code})"


def _call(expr: CallExpr) -> str:
    if isinstance(expr.operator, (SymbolRefExpr, UnresolvedSymbolExpr)):
        name = expr.operator.symbol.name
        args = [_expr(a) for a in expr.args]
        if name in _INFIX_OPS and len(args) >= 2:
            op = _INFIX_OPS[name]
            return f"({f' {op} '.join(args)})"
        if name in _INFIX_OPS and len(args) == 1:
            return f"({args[0]})"
        if name in _UNARY_OPS and len(args) == 1:
            return f"({_UNARY_OPS[name]}{args[0]})"
        if name == "list":
            return f"[{', '.join(args)}]"
        if name == "car":
            return f"({args[0]}[0])"
        if name == "cdr":
            return f"({args[0]}[1:])"
        if name == "cons":
            return f"[{args[0]}, *({args[1]})]" if len(args) == 2 else repr(args)
        if name == "apply":
            return f"({args[0]})(*({args[1]}))" if len(args) == 2 else repr(args)
        if name in _LITERAL_SYMBOLS:
            return _LITERAL_SYMBOLS[name]
        py_name = _mangle(name)
        return f"{py_name}({', '.join(args)})"
    func_code = _expr(expr.operator)
    args = [_expr(a) for a in expr.args]
    return f"({func_code})({', '.join(args)})"


def _assert(expr: AssertExpr) -> str:
    cond = _expr(expr.condition)
    if expr.message is not None:
        msg = _expr(expr.message)
        return f"(True if {cond} else (_ for _ in ()).throw(AssertionError({msg})))"
    return f"(True if {cond} else (_ for _ in ()).throw(AssertionError('assertion failed')))"


def _mangle(name: str) -> str:
    if name in _LITERAL_SYMBOLS:
        return _LITERAL_SYMBOLS[name]
    result = name.replace("-", "_").replace("?", "_p").replace("!", "_b")
    if result and result[0].isdigit():
        result = "_" + result
    return result
