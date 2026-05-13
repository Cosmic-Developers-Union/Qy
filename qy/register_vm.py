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
from qy.errors import QyEffectSignal
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.evaluator import Environment
from qy.evaluator import PureOperator
from qy.evaluator import QyContinuation
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
            case "LOAD_HOST":
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
            case "RUNTIME_EVAL":
                dest, form_reg = operands
                form = frame.registers[_register(form_reg)]
                frame.registers[_register(dest)] = await self._eval_form(form, frame.env)
            case "DEFINE_MODULE":
                dest, module_name, function_index = operands
                frame.registers[_register(dest)] = await self._define_module(
                    _symbol(module_name), _int(function_index), frame.env
                )
            case "FROM_IMPORT":
                module_name, specs = operands
                await self._from_import(_symbol(module_name), _tuple(specs), frame.env)
            case "DEFEFFECT":
                effect_name, resumable = operands
                await self._defeffect(_symbol(effect_name), bool(resumable), frame.env)
            case "PERFORM":
                dest, effect_sym, arg_reg = operands
                frame.registers[_register(dest)] = await self._perform(
                    frame, _register(dest), _symbol(effect_sym), frame.registers[_register(arg_reg)]
                )
            case "HANDLE":
                dest, body_fn_idx, handler_specs = operands
                frame.registers[_register(dest)] = await self._handle(
                    _int(body_fn_idx), _tuple(handler_specs), frame.env
                )
            case "RESUME":
                dest, cont_reg, value_reg = operands
                cont = frame.registers[_register(cont_reg)]
                value = frame.registers[_register(value_reg)]
                frame.registers[_register(dest)] = await self._resume(cont, value)
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
            case "RAISE_EFFECT":
                effect_name_sym, payload_register, resumable = operands
                effect_name = _symbol(effect_name_sym).name
                payload = frame.registers[_register(payload_register)]
                continuation = _make_identity_continuation(effect_name, bool(resumable))
                raise QyEffectSignal(
                    effect_name,
                    payload,
                    continuation,
                    resumable=bool(resumable),
                    span=instruction.span,
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
        if function.name.name == "<main>" or function.name.name == "<module-body>":
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

    async def _eval_form(self, form: object, env: Environment) -> object:
        from typing import cast

        from qy.ir import ProgramIR
        from qy.lowering import lower
        from qy.reader import Form
        from qy.reader import Symbol as _Symbol
        from qy.values import QyCons
        from qy.values import qy_cons_to_tuple

        if isinstance(form, QyCons):
            form = qy_cons_to_tuple(form)
        if not isinstance(form, _Symbol | tuple):
            return form
        program_ir = lower([cast(Form, form)], env)
        bytecode = compile_bytecode(ProgramIR(program_ir.body, program_ir.diagnostics))
        sub_vm = RegisterVirtualMachine(bytecode, env)
        result = await sub_vm.evaluate_program()
        return None if not result else result[-1]

    async def _define_module(
        self, module_name: Symbol, function_index: int, env: Environment
    ) -> object:
        from qy.macro import MacroDefinition
        from qy.source_modules import cache_source_module
        from qy.source_modules import lookup_source_module
        from qy.stdlib import register_module
        from qy.stdlib.module import StandardModule

        module_env = env.child()
        baseline = set(module_env.local_bindings())
        body_fn = BytecodeFunctionValue(self.program.functions[function_index], module_env)
        await self._run_function(body_fn, ())
        runtime_exports: dict[Symbol, object] = {}
        macro_exports: dict[Symbol, object] = {}
        for sym, value in module_env.local_bindings().items():
            if sym in baseline:
                continue
            if isinstance(value, MacroDefinition):
                macro_exports[sym] = value
            else:
                runtime_exports[sym] = value
        provisional = lookup_source_module(module_name.name, env)
        if provisional is not None:
            macro_exports = {**dict(provisional.macro_exports), **macro_exports}
        module = StandardModule(module_name.name, runtime_exports, macro_exports)
        register_module(module)
        cache_source_module(module, env)
        return env.define(module_name, module)

    async def _from_import(
        self, module_name: Symbol, specs: tuple[object, ...], env: Environment
    ) -> None:
        from qy.stdlib import load_module_async
        from qy.stdlib.imports import ImportSpec

        try:
            module = await load_module_async(module_name.name)
            for spec in specs:
                if not isinstance(spec, ImportSpec):
                    continue
                if spec.name in module.exports:
                    env.define(spec.alias, module.resolve(spec.name))
                elif spec.name not in module.macro_exports:
                    raise KeyError(f"module {module_name.name!r} has no export {spec.name.name!r}")
        except (KeyError, ValueError) as e:
            raise EvaluationError(str(e)) from e

    async def _defeffect(self, name: Symbol, resumable: bool, env: Environment) -> None:
        from qy.evaluator import EffectDefinition

        env.define(name, EffectDefinition(name, resumable))

    async def _perform(
        self,
        frame: _Frame,
        dest_reg: int,
        effect_sym: Symbol,
        arg: object,
    ) -> object:
        effect_name = effect_sym.name
        try:
            effect_def = frame.env.resolve(effect_sym)
            resumable = bool(getattr(effect_def, "resumable", True))
        except Exception:
            resumable = True

        if not resumable:
            continuation = _make_identity_continuation(effect_name, False)
            raise QyEffectSignal(effect_name, arg, continuation, resumable=False)

        # Capture current frame state to build a resumable continuation
        saved_registers = list(frame.registers)
        saved_env = frame.env
        saved_parents = list(frame.parents)
        saved_results = list(frame.results)
        saved_pc = frame.pc
        function_value = frame.function_value
        function = frame.function

        vm = self

        async def resume(value: object) -> object:
            resume_registers = list(saved_registers)
            resume_registers[dest_reg] = value
            resume_frame = _Frame(
                function_value,
                function,
                saved_pc,
                resume_registers,
                saved_env,
                list(saved_parents),
                list(saved_results),
            )
            while resume_frame.pc < len(resume_frame.function.instructions):
                inst = resume_frame.function.instructions[resume_frame.pc]
                resume_frame.pc += 1
                result = await vm._execute_instruction(resume_frame, inst)
                if isinstance(result, _FrameResult):
                    return result.value
                if isinstance(result, _Frame):
                    frame_result = await vm._run_function(result.function_value, ())
                    return frame_result.value
            return None

        continuation = QyContinuation(effect_name, True, resume)
        raise QyEffectSignal(effect_name, arg, continuation, resumable=True)

    async def _handle(
        self,
        body_fn_idx: int,
        handler_specs: tuple[object, ...],
        env: Environment,
    ) -> object:
        body_fn = BytecodeFunctionValue(self.program.functions[body_fn_idx], env)
        try:
            result = await self._run_function(body_fn, ())
            return result.value
        except QyEffectSignal as e:
            for spec in handler_specs:
                if not isinstance(spec, tuple) or len(spec) != 2:
                    continue
                effect_sym, handler_fn_idx = spec
                if not isinstance(effect_sym, Symbol) or not isinstance(handler_fn_idx, int):
                    continue
                if effect_sym.name == e.effect:
                    handler_fn = BytecodeFunctionValue(self.program.functions[handler_fn_idx], env)
                    handler_result = await self._run_function(handler_fn, (e.arg, e.continuation))
                    return handler_result.value
            raise

    async def _resume(self, continuation: object, value: object) -> object:
        from qy.evaluator import QyContinuation as _QyContinuation

        if not isinstance(continuation, _QyContinuation):
            raise QyRuntimeError(
                f"resume expects a continuation, got {continuation!r}",
                metadata={"value": continuation},
            )
        return await continuation.resume(value)


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


def _make_identity_continuation(effect_name: str, resumable: bool) -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation(effect_name, resumable, resume)


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
