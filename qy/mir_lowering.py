# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from qy.diagnostics import Diagnostic
from qy.errors import SourceSpan
from qy.ir import AllExpr
from qy.ir import ApplyExpr
from qy.ir import AssertExpr
from qy.ir import CacheExpr
from qy.ir import CallExpr
from qy.ir import CondExpr
from qy.ir import DefeffectExpr
from qy.ir import DefineExpr
from qy.ir import DefunExpr
from qy.ir import FromImportExpr
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
from qy.mir import MIRBlock
from qy.mir import MIRBlockId
from qy.mir import MIRConstantPool
from qy.mir import MIRFunction
from qy.mir import MIRInstruction
from qy.mir import MIROpcode
from qy.mir import MIRProgram
from qy.mir import MIRRegister
from qy.mir import MIRTerminator
from qy.mir import MIRTerminatorOpcode
from qy.reader import DottedTuple
from qy.reader import Symbol
from qy.values import list_to_qy_cons

__all__ = ["lower_mir"]


def lower_mir(program: ProgramIR) -> MIRProgram:
    lowerer = _MIRLowerer(tuple(program.diagnostics))
    return lowerer.lower(program)


@dataclass(slots=True)
class _LoweredExpression:
    register: MIRRegister | None


@dataclass(slots=True)
class _MutableBlock:
    id: MIRBlockId
    instructions: list[MIRInstruction]
    terminator: MIRTerminator | None = None

    @property
    def terminated(self) -> bool:
        return self.terminator is not None

    def finish(self) -> MIRBlock:
        terminator = self.terminator or MIRTerminator("RETURN", (None,))
        return MIRBlock(self.id, tuple(self.instructions), terminator)


class _FunctionLowerer:
    def __init__(self, owner: _MIRLowerer, name: Symbol, params: tuple[Symbol, ...]) -> None:
        self.owner = owner
        self.name = name
        self.params = params
        self.blocks: list[_MutableBlock] = []
        self.current = self.new_block()
        self.next_register = 0

    def lower_body(
        self,
        body: tuple[IRExpr, ...],
        *,
        collect_results: bool = False,
        tail: bool = False,
    ) -> MIRRegister | None:
        if not body:
            result = self.register()
            self.emit_load_const(result, None)
            return result
        last_register: MIRRegister | None = None
        for index, expression in enumerate(body):
            if self.current.terminated:
                break
            lowered = self.lower_expr(expression, tail=tail and index == len(body) - 1)
            last_register = lowered.register
            if collect_results and last_register is not None and not self.current.terminated:
                self.emit("APPEND_RESULT", last_register, span=_span_of(expression))
        if last_register is None and not self.current.terminated:
            last_register = self.register()
            self.emit_load_const(last_register, None)
        return last_register

    def lower_expr(self, expression: IRExpr, *, tail: bool = False) -> _LoweredExpression:
        if isinstance(expression, LiteralExpr):
            register = self.register()
            self.emit_load_const(register, expression.value, span=expression.span)
            return _LoweredExpression(register)
        if isinstance(expression, QuoteExpr):
            register = self.register()
            self.emit_load_const(register, _quote_data(expression.form), span=expression.span)
            return _LoweredExpression(register)
        if isinstance(expression, SymbolRefExpr | UnresolvedSymbolExpr):
            register = self.register()
            self.emit("LOAD_ENV", register, expression.symbol, span=expression.span)
            return _LoweredExpression(register)
        if isinstance(expression, DefunExpr):
            function_index = self.owner.lower_function(
                expression.name,
                expression.params,
                expression.body,
            )
            register = self.register()
            self.emit("MAKE_FUNCTION", register, function_index, span=expression.span)
            self.emit("DEFINE_ONCE", expression.name, register, span=expression.span)
            return _LoweredExpression(register)
        if isinstance(expression, LambdaExpr):
            function_index = self.owner.lower_function(
                Symbol("<lambda>"),
                expression.params,
                expression.body,
            )
            register = self.register()
            self.emit("MAKE_FUNCTION", register, function_index, span=expression.span)
            return _LoweredExpression(register)
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
            self.emit("DEFINE_ONCE", expression.name, register, span=expression.span)
            return _LoweredExpression(register)
        if isinstance(expression, LetExpr):
            return self.lower_let(expression, tail=tail)
        if isinstance(expression, CondExpr):
            return self.lower_cond(expression, tail=tail)
        if isinstance(expression, CallExpr):
            return self.lower_call(expression, tail=tail)
        if isinstance(expression, AssertExpr):
            return self.lower_assert(expression, tail=tail)
        if isinstance(expression, RuntimeEvalExpr):
            return self.lower_runtime_eval(expression)
        if isinstance(expression, ModuleExpr):
            return self.lower_module(expression)
        if isinstance(expression, FromImportExpr):
            return self.lower_from_import(expression)
        if isinstance(expression, DefeffectExpr):
            return self.lower_defeffect(expression)
        if isinstance(expression, PerformExpr):
            return self.lower_perform(expression)
        if isinstance(expression, HandleExpr):
            return self.lower_handle(expression)
        if isinstance(expression, ResumeExpr):
            return self.lower_resume(expression)
        if isinstance(expression, DefineExpr):
            return self.lower_define(expression)
        if isinstance(expression, PipelineExpr):
            return self.lower_pipeline(expression, tail=tail)
        if isinstance(expression, ParallelExpr | AllExpr):
            return self.lower_parallel_all(expression, tail=tail)
        if isinstance(expression, RaceExpr):
            return self.lower_race(expression, tail=tail)
        if isinstance(expression, ApplyExpr):
            return self.lower_apply(expression, tail=tail)
        if isinstance(expression, CacheExpr):
            return self.lower_cache(expression)

        self.owner.diagnostic(f"MIR lowering does not support {type(expression).__name__}")
        return _LoweredExpression(None)

    def lower_let(self, expression: LetExpr, *, tail: bool) -> _LoweredExpression:
        self.emit("ENTER_SCOPE", span=expression.span)
        for binding in expression.bindings:
            value = self.lower_expr(binding.value)
            if value.register is not None and not self.current.terminated:
                self.emit(
                    "STORE_LOCAL", binding.symbol, value.register, span=_span_of(binding.value)
                )
        result = self.lower_body(expression.body, tail=tail)
        if not self.current.terminated:
            self.emit("EXIT_SCOPE", span=expression.span)
        return _LoweredExpression(result)

    def lower_cond(self, expression: CondExpr, *, tail: bool) -> _LoweredExpression:
        result_register = None if tail else self.register()
        end_block = None if tail else self.new_block()
        for clause in expression.clauses:
            condition = self.lower_expr(clause.condition)
            if condition.register is None:
                continue
            then_block = self.new_block()
            next_block = self.new_block()
            self.terminate(
                "BRANCH",
                condition.register,
                then_block.id,
                next_block.id,
                span=_span_of(clause.condition),
            )

            self.switch_to(then_block)
            result = self.lower_expr(clause.result, tail=tail)
            if result.register is not None and not self.current.terminated:
                if tail:
                    self.terminate("RETURN", result.register, span=_span_of(clause.result))
                elif result_register is not None and end_block is not None:
                    self.emit(
                        "MOVE", result_register, result.register, span=_span_of(clause.result)
                    )
                    self.terminate("JUMP", end_block.id, span=_span_of(clause.result))

            self.switch_to(next_block)

        if tail:
            default = self.register()
            self.emit_load_const(default, None, span=expression.span)
            self.terminate("RETURN", default, span=expression.span)
            return _LoweredExpression(None)

        assert result_register is not None
        assert end_block is not None
        default = self.register()
        self.emit_load_const(default, None, span=expression.span)
        self.emit("MOVE", result_register, default, span=expression.span)
        self.terminate("JUMP", end_block.id, span=expression.span)
        self.switch_to(end_block)
        return _LoweredExpression(result_register)

    def lower_call(self, expression: CallExpr, *, tail: bool) -> _LoweredExpression:
        operator = self.lower_expr(expression.operator)
        arg_registers: list[MIRRegister] = []
        for arg in expression.args:
            lowered_arg = self.lower_expr(arg)
            if lowered_arg.register is not None:
                arg_registers.append(lowered_arg.register)
        if operator.register is None:
            return _LoweredExpression(None)
        if tail and expression.tail_position:
            self.terminate(
                "TAIL_CALL",
                operator.register,
                tuple(arg_registers),
                span=expression.span,
            )
            return _LoweredExpression(None)
        result = self.register()
        self.emit("CALL", result, operator.register, tuple(arg_registers), span=expression.span)
        return _LoweredExpression(result)

    def lower_assert(self, expression: AssertExpr, *, tail: bool) -> _LoweredExpression:
        condition = self.lower_expr(expression.condition)
        if condition.register is None:
            return _LoweredExpression(None)

        pass_block = self.new_block()
        fail_block = self.new_block()
        self.terminate(
            "BRANCH",
            condition.register,
            pass_block.id,
            fail_block.id,
            span=_span_of(expression.condition),
        )

        self.switch_to(fail_block)
        if expression.message is not None:
            msg_result = self.lower_expr(expression.message)
            msg_reg = msg_result.register
        else:
            msg_reg = None
        if msg_reg is None:
            msg_reg = self.register()
            self.emit_load_const(msg_reg, Symbol("assertion failed"), span=expression.span)
        if not self.current.terminated:
            self.terminate(
                "RAISE_EFFECT",
                Symbol("assert-failed"),
                msg_reg,
                False,
                span=expression.span,
            )

        self.switch_to(pass_block)
        if tail:
            self.terminate("RETURN", condition.register, span=expression.span)
            return _LoweredExpression(None)

        result_register = self.register()
        end_block = self.new_block()
        self.emit("MOVE", result_register, condition.register, span=expression.span)
        self.terminate("JUMP", end_block.id, span=expression.span)
        self.switch_to(end_block)
        return _LoweredExpression(result_register)

    def lower_runtime_eval(self, expression: RuntimeEvalExpr) -> _LoweredExpression:
        inner = self.lower_expr(expression.expression)
        if inner.register is None:
            return _LoweredExpression(None)
        result = self.register()
        self.emit("RUNTIME_EVAL", result, inner.register, span=expression.span)
        return _LoweredExpression(result)

    def lower_module(self, expression: ModuleExpr) -> _LoweredExpression:
        function_index = self.owner.lower_function(
            Symbol("<module-body>"),
            (),
            expression.body,
        )
        result = self.register()
        self.emit(
            "DEFINE_MODULE",
            result,
            expression.name,
            function_index,
            expression.export_names,
            span=expression.span,
        )
        return _LoweredExpression(result)

    def lower_from_import(self, expression: FromImportExpr) -> _LoweredExpression:
        self.emit("FROM_IMPORT", expression.module, expression.specs, span=expression.span)
        return _LoweredExpression(None)

    def lower_defeffect(self, expression: DefeffectExpr) -> _LoweredExpression:
        self.emit("DEFEFFECT", expression.name, expression.resumable, span=expression.span)
        return _LoweredExpression(None)

    def lower_perform(self, expression: PerformExpr) -> _LoweredExpression:
        arg = self.lower_expr(expression.argument)
        if arg.register is None:
            return _LoweredExpression(None)
        result = self.register()
        self.emit("PERFORM", result, expression.effect, arg.register, span=expression.span)
        return _LoweredExpression(result)

    def lower_handle(self, expression: HandleExpr) -> _LoweredExpression:
        body_fn_idx = self.owner.lower_function(
            Symbol("<handle-body>"),
            (),
            (expression.expression,),
        )
        handler_specs: list[tuple[object, ...]] = []
        for handler in expression.handlers:
            handler_fn_idx = self.owner.lower_function(
                Symbol(f"<handler-{handler.effect.name}>"),
                (handler.arg_name, handler.continuation_name),
                handler.body,
            )
            handler_specs.append((handler.effect, handler_fn_idx))
        result = self.register()
        self.emit(
            "HANDLE",
            result,
            body_fn_idx,
            tuple(handler_specs),
            span=expression.span,
        )
        return _LoweredExpression(result)

    def lower_resume(self, expression: ResumeExpr) -> _LoweredExpression:
        cont = self.lower_expr(expression.continuation)
        value = self.lower_expr(expression.value)
        if cont.register is None or value.register is None:
            return _LoweredExpression(None)
        result = self.register()
        self.emit("RESUME", result, cont.register, value.register, span=expression.span)
        return _LoweredExpression(result)

    def lower_pipeline(self, expression: PipelineExpr, *, tail: bool) -> _LoweredExpression:
        result = self.lower_body(expression.body, tail=tail)
        return _LoweredExpression(result)

    def lower_parallel_all(
        self, expression: ParallelExpr | AllExpr, *, tail: bool
    ) -> _LoweredExpression:
        opcode = "PARALLEL_GATHER" if isinstance(expression, ParallelExpr) else "ALL_GATHER"
        thunk_indices: list[int] = []
        for expr in expression.exprs:
            thunk_index = self.owner.lower_function(
                Symbol("<parallel-thunk>"),
                (),
                (expr,),
            )
            thunk_indices.append(thunk_index)
        result = self.register()
        self.emit(opcode, result, *thunk_indices, span=expression.span)
        if tail and not self.current.terminated:
            self.terminate("RETURN", result, span=expression.span)
            return _LoweredExpression(None)
        return _LoweredExpression(result)

    def lower_race(self, expression: RaceExpr, *, tail: bool) -> _LoweredExpression:
        if not expression.exprs:
            result = self.register()
            self.emit_load_const(result, None, span=expression.span)
            return _LoweredExpression(result)
        thunk_indices: list[int] = []
        for expr in expression.exprs:
            thunk_index = self.owner.lower_function(
                Symbol("<race-thunk>"),
                (),
                (expr,),
            )
            thunk_indices.append(thunk_index)
        result = self.register()
        self.emit("RACE_FIRST", result, *thunk_indices, span=expression.span)
        if tail and not self.current.terminated:
            self.terminate("RETURN", result, span=expression.span)
            return _LoweredExpression(None)
        return _LoweredExpression(result)

    def lower_apply(self, expression: ApplyExpr, *, tail: bool) -> _LoweredExpression:
        func = self.lower_expr(expression.function)
        args = self.lower_expr(expression.args)
        if func.register is None or args.register is None:
            return _LoweredExpression(None)
        result = self.register()
        self.emit("APPLY", result, func.register, args.register, span=expression.span)
        return _LoweredExpression(result)

    def lower_cache(self, expression: CacheExpr) -> _LoweredExpression:
        thunk_index = self.owner.lower_function(
            Symbol("<cache-thunk>"),
            (),
            (expression.expression,),
        )
        result = self.register()
        self.emit("CACHE_EVAL", result, expression.cache_key, thunk_index, span=expression.span)
        return _LoweredExpression(result)

    def lower_define(self, expression: DefineExpr) -> _LoweredExpression:
        register = self.register()

        if isinstance(expression.value, DefeffectExpr):
            self.emit(
                "DEFEFFECT", expression.name, expression.value.resumable, span=expression.span
            )
            self.emit("LOAD_ENV", register, expression.name, span=expression.span)
            return _LoweredExpression(register)

        if isinstance(expression.value, LambdaExpr):
            function_index = self.owner.lower_function(
                expression.name,
                expression.value.params,
                expression.value.body,
            )
            self.emit("MAKE_FUNCTION", register, function_index, span=expression.span)
        else:
            value = self.lower_expr(expression.value)
            if value.register is not None and not self.current.terminated:
                self.emit("MOVE", register, value.register, span=expression.span)

        self.emit("DEFINE_ONCE", expression.name, register, span=expression.span)
        return _LoweredExpression(register)

    def new_block(self) -> _MutableBlock:
        block = _MutableBlock(len(self.blocks), [])
        self.blocks.append(block)
        return block

    def switch_to(self, block: _MutableBlock) -> None:
        self.current = block

    def register(self) -> MIRRegister:
        register = self.next_register
        self.next_register += 1
        return register

    def emit(
        self,
        opcode: MIROpcode,
        *operands: object,
        span: SourceSpan | None = None,
    ) -> None:
        if self.current.terminated:
            return
        self.current.instructions.append(MIRInstruction(opcode, tuple(operands), span))

    def emit_load_const(
        self,
        dest: MIRRegister,
        value: object,
        *,
        span: SourceSpan | None = None,
    ) -> None:
        idx = self.owner.constants.intern(value)
        self.emit("LOAD_CONST", dest, idx, span=span)

    def terminate(
        self,
        opcode: MIRTerminatorOpcode,
        *operands: object,
        span: SourceSpan | None = None,
    ) -> None:
        if self.current.terminated:
            return
        self.current.terminator = MIRTerminator(opcode, tuple(operands), span)

    def finish(self) -> MIRFunction:
        return MIRFunction(
            self.name,
            self.params,
            self.next_register,
            tuple(block.finish() for block in self.blocks),
            0,
        )


class _MIRLowerer:
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = list(diagnostics)
        self.functions: list[MIRFunction | None] = []
        self.constants = MIRConstantPool()

    def lower(self, program: ProgramIR) -> MIRProgram:
        main_index = self.reserve_function()
        main = _FunctionLowerer(self, Symbol("<main>"), ())
        result = main.lower_body(program.body, collect_results=True)
        if result is None and not main.current.terminated:
            result = main.register()
            main.emit_load_const(result, None)
        if result is not None and not main.current.terminated:
            main.terminate("RETURN", result)
        self.functions[main_index] = main.finish()
        return MIRProgram(
            tuple(function for function in self.functions if function is not None),
            self.constants,
            main_index,
            tuple(self.diagnostics),
        )

    def lower_function(
        self,
        name: Symbol,
        params: tuple[Symbol, ...],
        body: tuple[IRExpr, ...],
    ) -> int:
        function_index = self.reserve_function()
        function = _FunctionLowerer(self, name, params)
        result = function.lower_body(body, tail=True)
        if result is not None and not function.current.terminated:
            function.terminate("RETURN", result)
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
