# coding: utf-8

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeFunctionValue
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.bytecode import Register
from qy.bytecode_compiler import compile_bytecode
from qy.errors import EvaluationError
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.evaluator import Environment
from qy.evaluator import PureOperator
from qy.evaluator import run_async
from qy.evaluator import standard_environment
from qy.ir import ProgramIR
from qy.lowering import lower
from qy.macroexpand import macroexpand_source_async
from qy.operator_runtime import runtime_operator_semantics
from qy.operator_runtime import validate_operator_arity
from qy.reader import Symbol
from qy.values import QY_NIL
from qy.virtual_stack import VirtualStack
from qy.virtual_stack import VirtualStackFrame

__all__ = [
    "RegisterVirtualMachine",
    "evaluate_bytecode",
    "evaluate_bytecode_async",
    "evaluate_bytecode_source",
    "evaluate_bytecode_source_async",
]

_COMPILE_TIME_MACRO = object()


@dataclass(slots=True)
class _Frame:
    function_value: BytecodeFunctionValue
    function: BytecodeFunction
    pc: int
    registers: list[object]
    env: Environment
    parents: list[Environment]
    results: list[object]


@dataclass(frozen=True, slots=True)
class _FrameResult:
    value: object
    results: tuple[object, ...]


class RegisterVirtualMachine:
    def __init__(self, program: BytecodeProgram, env: Environment | None = None) -> None:
        self.program = program
        self.env = env or standard_environment()
        self.stack = VirtualStack()

    async def evaluate_program(self) -> list[object]:
        _raise_for_diagnostics(self.program)
        main = BytecodeFunctionValue(self.program.functions[self.program.main], self.env)
        result = await self._run_function(main, (), collect_results=True)
        return list(result.results)

    async def evaluate(self) -> object:
        results = await self.evaluate_program()
        return None if not results else results[-1]

    async def _run_function(
        self,
        function_value: BytecodeFunctionValue,
        args: tuple[object, ...],
        *,
        collect_results: bool = False,
        call_span: SourceSpan | None = None,
    ) -> _FrameResult:
        frame = self._make_frame(function_value, args, collect_results=collect_results)
        with self.stack.frame(_function_stack_frame(frame.function, call_span)):
            try:
                while True:
                    self.stack.replace_top(_function_stack_frame(frame.function, call_span))
                    instruction = frame.function.instructions[frame.pc]
                    frame.pc += 1
                    result = await self._execute_instruction(frame, instruction)
                    if isinstance(result, _FrameResult):
                        return result
                    if isinstance(result, _Frame):
                        frame = result
            except EvaluationError as e:
                self._attach_virtual_stack(e)
                raise

    async def _execute_instruction(
        self,
        frame: _Frame,
        instruction: Instruction,
    ) -> _FrameResult | _Frame | None:
        operands = instruction.operands
        match instruction.opcode:
            case "LOAD_CONST":
                dest, value = operands
                frame.registers[_register(dest)] = value
            case "LOAD_ENV":
                dest, symbol = operands
                frame.registers[_register(dest)] = frame.env.resolve(_symbol(symbol))
            case "MOVE":
                dest, source = operands
                frame.registers[_register(dest)] = frame.registers[_register(source)]
            case "STORE_LOCAL":
                symbol, source = operands
                value = frame.registers[_register(source)]
                if value is _COMPILE_TIME_MACRO:
                    return None
                frame.env.define(_symbol(symbol), value)
            case "MAKE_FUNCTION":
                dest, function_index = operands
                frame.registers[_register(dest)] = BytecodeFunctionValue(
                    self.program.functions[_int(function_index)],
                    frame.env,
                )
            case "MAKE_MACRO":
                dest, name, params, raw_body = operands
                del name, params, raw_body
                frame.registers[_register(dest)] = _COMPILE_TIME_MACRO
            case "ENTER_SCOPE":
                frame.parents.append(frame.env)
                frame.env = frame.env.child()
            case "EXIT_SCOPE":
                frame.env = frame.parents.pop()
            case "APPEND_RESULT":
                (source,) = operands
                value = frame.registers[_register(source)]
                frame.results.append(None if value is _COMPILE_TIME_MACRO else value)
            case "JUMP":
                (target,) = operands
                frame.pc = _int(target)
            case "JUMP_IF_FALSE":
                source, target = operands
                if not _truthy(frame.registers[_register(source)]):
                    frame.pc = _int(target)
            case "CALL":
                dest, callee_register, arg_registers = operands
                args = tuple(frame.registers[_register(item)] for item in _registers(arg_registers))
                frame.registers[_register(dest)] = await self._call(
                    frame.registers[_register(callee_register)],
                    args,
                    instruction.span,
                )
            case "TAIL_CALL":
                callee_register, arg_registers = operands
                args = tuple(frame.registers[_register(item)] for item in _registers(arg_registers))
                callee = frame.registers[_register(callee_register)]
                if isinstance(callee, BytecodeFunctionValue):
                    return self._make_frame(callee, args, collect_results=False)
                return _FrameResult(await self._call(callee, args, instruction.span), ())
            case "RETURN":
                (source,) = operands
                value = frame.registers[_register(source)]
                return _FrameResult(
                    None if value is _COMPILE_TIME_MACRO else value,
                    tuple(frame.results),
                )
        return None

    async def _call(
        self,
        callee: object,
        args: tuple[object, ...],
        span: SourceSpan | None,
    ) -> object:
        if isinstance(callee, BytecodeFunctionValue):
            return (await self._run_function(callee, args, call_span=span)).value
        semantics = runtime_operator_semantics(callee)
        if semantics.argument_mode != "eager":
            raise QyRuntimeError(
                "bytecode VM only supports eager operators in host-call compatibility mode",
                span=span,
                metadata={"operator": getattr(callee, "name", None)},
            )
        validate_operator_arity(callee, len(args), span=span)
        if isinstance(callee, PureOperator):
            try:
                return await _await_if_needed(callee(*args))
            except EvaluationError:
                raise
            except Exception as e:
                raise QyRuntimeError(
                    str(e),
                    span=span,
                    cause=e,
                    metadata={"python_exception": type(e).__name__},
                ) from e
        if callable(callee):
            host_callable = cast(Callable[..., object], callee)
            return await _await_if_needed(host_callable(*args))
        raise QyTypeError(
            f"bytecode call resolved to non-callable {callee!r}",
            span=span,
            metadata={"callee": callee},
        )

    def _make_frame(
        self,
        function_value: BytecodeFunctionValue,
        args: tuple[object, ...],
        *,
        collect_results: bool,
    ) -> _Frame:
        function = function_value.function
        if len(args) != len(function.params):
            raise QyRuntimeError(
                f"{function.name.name} expects {len(function.params)} arguments, got {len(args)}",
                metadata={
                    "expected": len(function.params),
                    "actual": len(args),
                    "function": function.name.name,
                },
            )
        if function.name.name == "<main>":
            env = function_value.closure
        else:
            env = function_value.closure.child(dict(zip(function.params, args, strict=True)))
        return _Frame(
            function_value,
            function,
            0,
            [None] * function.register_count,
            env,
            [],
            [],
        )

    def _attach_virtual_stack(self, error: EvaluationError) -> None:
        if error.frames:
            return
        for frame in self.stack.trace():
            error.add_frame(frame)


def evaluate_bytecode(program: BytecodeProgram, env: Environment | None = None) -> object:
    return run_async(evaluate_bytecode_async(program, env))


async def evaluate_bytecode_async(
    program: BytecodeProgram,
    env: Environment | None = None,
) -> object:
    return await RegisterVirtualMachine(program, env).evaluate()


def evaluate_bytecode_source(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> object:
    return run_async(evaluate_bytecode_source_async(source, env, source_name=source_name))


async def evaluate_bytecode_source_async(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> object:
    runtime_env = env or standard_environment()
    expansion = await macroexpand_source_async(source, runtime_env, source_name=source_name)
    program_ir = lower(expansion.forms, runtime_env)
    diagnostics = (*expansion.diagnostics, *program_ir.diagnostics)
    bytecode = compile_bytecode(ProgramIR(program_ir.body, diagnostics))
    return await evaluate_bytecode_async(bytecode, runtime_env)


def _raise_for_diagnostics(program: BytecodeProgram) -> None:
    diagnostics = tuple(item for item in program.diagnostics if item.severity == "error")
    if not diagnostics:
        return
    messages = "; ".join(item.message for item in diagnostics)
    raise QyRuntimeError(f"cannot execute bytecode with diagnostics: {messages}")


def _function_stack_frame(
    function: BytecodeFunction,
    span: SourceSpan | None,
) -> VirtualStackFrame:
    name = (
        None
        if function.name.name == "<lambda>" or function.name.name == "<main>"
        else function.name.name
    )
    kind = "lambda" if function.name.name == "<lambda>" else "call"
    return VirtualStackFrame(kind, name, span)


def _truthy(value: object) -> bool:
    return value is not False and value is not None and value is not QY_NIL and value != ()


async def _await_if_needed(value: object) -> object:
    if inspect.iscoroutine(value):
        return await value
    return value


def _register(value: object) -> Register:
    if not isinstance(value, int):
        raise TypeError(f"expected register, got {value!r}")
    return value


def _registers(value: object) -> tuple[Register, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"expected register tuple, got {value!r}")
    return tuple(_register(item) for item in value)


def _symbol(value: object) -> Symbol:
    if not isinstance(value, Symbol):
        raise TypeError(f"expected symbol, got {value!r}")
    return value


def _symbols(value: object) -> tuple[Symbol, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"expected symbol tuple, got {value!r}")
    return tuple(_symbol(item) for item in value)


def _tuple(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"expected tuple, got {value!r}")
    return value


def _int(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError(f"expected int, got {value!r}")
    return value
