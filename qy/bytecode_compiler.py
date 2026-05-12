# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.bytecode import Opcode
from qy.bytecode import Register
from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefunExpr
from qy.ir import IRExpr
from qy.ir import LambdaExpr
from qy.ir import LetExpr
from qy.ir import LiteralExpr
from qy.ir import MacroExpr
from qy.ir import ProgramIR
from qy.ir import QuoteExpr
from qy.ir import SymbolRefExpr
from qy.ir import UnresolvedSymbolExpr
from qy.reader import DottedTuple
from qy.reader import Symbol
from qy.values import list_to_qy_cons

__all__ = ["compile_bytecode"]


def compile_bytecode(program: ProgramIR) -> BytecodeProgram:
    compiler = _BytecodeCompiler(tuple(program.diagnostics))
    return compiler.compile(program)


@dataclass(slots=True)
class _CompiledExpression:
    register: Register | None


class _FunctionCompiler:
    def __init__(self, owner: _BytecodeCompiler, name: Symbol, params: tuple[Symbol, ...]) -> None:
        self.owner = owner
        self.name = name
        self.params = params
        self.instructions: list[Instruction] = []
        self.next_register = 0

    def compile_body(
        self,
        body: tuple[IRExpr, ...],
        *,
        collect_results: bool = False,
        tail: bool = False,
    ) -> Register | None:
        if not body:
            result = self.register()
            self.emit("LOAD_CONST", result, None)
            return result
        last_register: Register | None = None
        for index, expression in enumerate(body):
            compiled = self.compile_expr(expression, tail=tail and index == len(body) - 1)
            last_register = compiled.register
            if collect_results and last_register is not None:
                self.emit("APPEND_RESULT", last_register, span=_span_of(expression))
        return last_register

    def compile_expr(self, expression: IRExpr, *, tail: bool = False) -> _CompiledExpression:
        if isinstance(expression, LiteralExpr):
            register = self.register()
            self.emit("LOAD_CONST", register, expression.value, span=expression.span)
            return _CompiledExpression(register)
        if isinstance(expression, QuoteExpr):
            register = self.register()
            self.emit("LOAD_CONST", register, _quote_data(expression.form), span=expression.span)
            return _CompiledExpression(register)
        if isinstance(expression, SymbolRefExpr | UnresolvedSymbolExpr):
            register = self.register()
            self.emit("LOAD_ENV", register, expression.symbol, span=expression.span)
            return _CompiledExpression(register)
        if isinstance(expression, DefunExpr):
            function_index = self.owner.compile_function(
                expression.name,
                expression.params,
                expression.body,
            )
            register = self.register()
            self.emit("MAKE_FUNCTION", register, function_index, span=expression.span)
            self.emit("STORE_LOCAL", expression.name, register, span=expression.span)
            return _CompiledExpression(register)
        if isinstance(expression, LambdaExpr):
            function_index = self.owner.compile_function(
                Symbol("<lambda>"),
                expression.params,
                expression.body,
            )
            register = self.register()
            self.emit("MAKE_FUNCTION", register, function_index, span=expression.span)
            return _CompiledExpression(register)
        if isinstance(expression, MacroExpr):
            register = self.register()
            self.emit(
                "MAKE_MACRO",
                register,
                expression.name,
                expression.params,
                expression.raw_body,
                span=expression.span,
            )
            self.emit("STORE_LOCAL", expression.name, register, span=expression.span)
            return _CompiledExpression(register)
        if isinstance(expression, LetExpr):
            return self.compile_let(expression, tail=tail)
        if isinstance(expression, CondExpr):
            return self.compile_cond(expression, tail=tail)
        if isinstance(expression, CallExpr):
            return self.compile_call(expression, tail=tail)

        self.owner.diagnostic(f"bytecode compiler does not support {type(expression).__name__}")
        register = self.register()
        self.emit("LOAD_CONST", register, None, span=_span_of(expression))
        return _CompiledExpression(register)

    def compile_let(self, expression: LetExpr, *, tail: bool) -> _CompiledExpression:
        self.emit("ENTER_SCOPE", span=expression.span)
        for binding in expression.bindings:
            value = self.compile_expr(binding.value)
            if value.register is not None:
                self.emit(
                    "STORE_LOCAL", binding.symbol, value.register, span=_span_of(binding.value)
                )
        result = self.compile_body(expression.body, tail=tail)
        if result is not None:
            self.emit("EXIT_SCOPE", span=expression.span)
        return _CompiledExpression(result)

    def compile_cond(self, expression: CondExpr, *, tail: bool) -> _CompiledExpression:
        result_register = None if tail else self.register()
        end_jumps: list[int] = []
        for clause in expression.clauses:
            condition = self.compile_expr(clause.condition)
            if condition.register is None:
                continue
            jump_if_false = self.emit(
                "JUMP_IF_FALSE",
                condition.register,
                None,
                span=_span_of(clause.condition),
            )
            result = self.compile_expr(clause.result, tail=tail)
            if result.register is not None:
                if tail:
                    self.emit("RETURN", result.register, span=_span_of(clause.result))
                elif result_register is not None:
                    self.emit(
                        "MOVE", result_register, result.register, span=_span_of(clause.result)
                    )
                    end_jumps.append(self.emit("JUMP", None, span=_span_of(clause.result)))
            self.patch(jump_if_false, len(self.instructions))
        if result_register is None:
            return _CompiledExpression(None)
        default = self.register()
        self.emit("LOAD_CONST", default, None, span=expression.span)
        self.emit("MOVE", result_register, default, span=expression.span)
        end = len(self.instructions)
        for jump in end_jumps:
            self.patch(jump, end)
        return _CompiledExpression(result_register)

    def compile_call(self, expression: CallExpr, *, tail: bool) -> _CompiledExpression:
        operator = self.compile_expr(expression.operator)
        arg_registers: list[Register] = []
        for arg in expression.args:
            compiled_arg = self.compile_expr(arg)
            if compiled_arg.register is not None:
                arg_registers.append(compiled_arg.register)
        if operator.register is None:
            return _CompiledExpression(None)
        if tail and expression.tail_position:
            self.emit("TAIL_CALL", operator.register, tuple(arg_registers), span=expression.span)
            return _CompiledExpression(None)
        result = self.register()
        self.emit("CALL", result, operator.register, tuple(arg_registers), span=expression.span)
        return _CompiledExpression(result)

    def register(self) -> Register:
        register = self.next_register
        self.next_register += 1
        return register

    def emit(self, opcode: Opcode, *operands: object, span: SourceSpan | None = None) -> int:
        index = len(self.instructions)
        self.instructions.append(Instruction(opcode, tuple(operands), span))
        return index

    def patch(self, index: int, target: int) -> None:
        instruction = self.instructions[index]
        operands = (*instruction.operands[:-1], target)
        self.instructions[index] = Instruction(instruction.opcode, operands, instruction.span)

    def finish(self) -> BytecodeFunction:
        return BytecodeFunction(
            self.name,
            self.params,
            self.next_register,
            tuple(self.instructions),
        )


class _BytecodeCompiler:
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = list(diagnostics)
        self.functions: list[BytecodeFunction | None] = []

    def compile(self, program: ProgramIR) -> BytecodeProgram:
        main_index = self.reserve_function()
        main = _FunctionCompiler(self, Symbol("<main>"), ())
        result = main.compile_body(program.body, collect_results=True)
        if result is None:
            result = main.register()
            main.emit("LOAD_CONST", result, None)
        main.emit("RETURN", result)
        self.functions[main_index] = main.finish()
        return BytecodeProgram(
            tuple(function for function in self.functions if function is not None),
            main_index,
            tuple(self.diagnostics),
        )

    def compile_function(
        self,
        name: Symbol,
        params: tuple[Symbol, ...],
        body: tuple[IRExpr, ...],
    ) -> int:
        function_index = self.reserve_function()
        function = _FunctionCompiler(self, name, params)
        result = function.compile_body(body, tail=True)
        if result is not None:
            function.emit("RETURN", result)
        self.functions[function_index] = function.finish()
        return function_index

    def reserve_function(self) -> int:
        index = len(self.functions)
        self.functions.append(None)
        return index

    def diagnostic(self, message: str) -> None:
        self.diagnostics.append(Diagnostic(message))


def _span_of(expression: object) -> SourceSpan | None:
    return cast(SourceSpan | None, getattr(expression, "span", None))


def _quote_data(value: object) -> object:
    if isinstance(value, DottedTuple):
        return list_to_qy_cons((_quote_data(item) for item in value), _quote_data(value.tail))
    if isinstance(value, tuple):
        return list_to_qy_cons(_quote_data(item) for item in value)
    return value
