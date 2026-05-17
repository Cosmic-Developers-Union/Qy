# coding: utf-8

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from qy.async_runtime import run_async
from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeFunctionValue
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.bytecode import Register
from qy.bytecode_compiler import compile_bytecode
from qy.continuation import QyContinuation
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
from qy.errors import QyEffectSignal
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.ir import ProgramIR
from qy.lowering import lower
from qy.macroexpand import macroexpand_source_async
from qy.operator_runtime import runtime_operator_semantics
from qy.operator_runtime import validate_operator_arity
from qy.operators import PureOperator
from qy.reader import Symbol
from qy.runtime_values import EffectDefinition
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


@dataclass(frozen=True, slots=True)
class _EffectFrame:
    """Captured frame state for effect continuation.

    When an effect is performed, the current frame state must be saved so that
    the effect handler can resume execution at this point with a value.
    This data structure explicitly models the saved frame state.
    """

    registers: tuple[object, ...]
    env: Environment
    pc: int
    parents: tuple[Environment, ...]
    results: tuple[object, ...]
    function_value: BytecodeFunctionValue
    function: BytecodeFunction


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
            case "DEFINE_ONCE":
                symbol, source = operands
                value = frame.registers[_register(source)]
                if value is _COMPILE_TIME_MACRO:
                    return None
                frame.env.define_once(_symbol(symbol), value)
            case "MAKE_FUNCTION":
                dest, function_index = operands
                frame.registers[_register(dest)] = BytecodeFunctionValue(
                    self.program.functions[_int(function_index)],
                    frame.env,
                    self.program,
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
            case "BUILD_TUPLE":
                dest = operands[0]
                values = tuple(frame.registers[_register(r)] for r in operands[1:])
                frame.registers[_register(dest)] = values
            case "APPLY":
                dest, func_reg, args_reg = operands
                func = frame.registers[_register(func_reg)]
                args_val = frame.registers[_register(args_reg)]
                args = tuple(_sequence_to_args(args_val))
                frame.registers[_register(dest)] = await self._call(
                    func, args, instruction.span, frame.env
                )
            case "RUNTIME_EVAL":
                dest, form_reg = operands
                form = frame.registers[_register(form_reg)]
                frame.registers[_register(dest)] = await self._eval_form(form, frame.env)
            case "PARALLEL_GATHER":
                dest, *thunk_indices = operands
                frame.registers[_register(dest)] = await self._parallel_gather(
                    [_int(i) for i in thunk_indices], frame.env, aggregate_errors=True
                )
            case "ALL_GATHER":
                dest, *thunk_indices = operands
                frame.registers[_register(dest)] = await self._parallel_gather(
                    [_int(i) for i in thunk_indices], frame.env, aggregate_errors=False
                )
            case "RACE_FIRST":
                dest, *thunk_indices = operands
                frame.registers[_register(dest)] = await self._race_first(
                    [_int(i) for i in thunk_indices], frame.env
                )
            case "CACHE_EVAL":
                dest, cache_key, thunk_idx = operands
                frame.registers[_register(dest)] = await self._cache_eval(
                    cache_key, _int(thunk_idx), frame.env
                )
            case "DEFINE_MODULE":
                dest, module_name, function_index, export_names = operands
                frame.registers[_register(dest)] = await self._define_module(
                    _symbol(module_name),
                    _int(function_index),
                    frame.env,
                    export_names=_symbols(export_names) if isinstance(export_names, tuple) else (),
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
                    frame.env,
                )
            case "TAIL_CALL":
                callee_register, arg_registers = operands
                args = tuple(frame.registers[_register(item)] for item in _registers(arg_registers))
                callee = frame.registers[_register(callee_register)]
                if isinstance(callee, BytecodeFunctionValue):
                    return self._make_frame(callee, args, collect_results=False)
                return _FrameResult(await self._call(callee, args, instruction.span, frame.env), ())
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
        env: Environment | None = None,
    ) -> object:
        if isinstance(callee, BytecodeFunctionValue):
            return (await self._run_function(callee, args, call_span=span)).value
        semantics = runtime_operator_semantics(callee)
        if semantics.argument_mode != "eager":
            if env is None:
                raise QyRuntimeError(
                    "bytecode VM only supports eager operators in host-call compatibility mode",
                    span=span,
                    metadata={"operator": getattr(callee, "name", None)},
                )
            if isinstance(callee, PureOperator) and callee.argument_evaluator is not None:
                processed = cast(
                    tuple[object, ...],
                    await _await_if_needed(callee.argument_evaluator(args, env)),
                )
                return await _await_if_needed(callee.func(*processed))
            func = getattr(callee, "func", None)
            if callable(func):
                result = func(args, env)
                return await _await_if_needed(result)
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

    async def _parallel_gather(
        self,
        thunk_indices: list[int],
        env: Environment,
        *,
        aggregate_errors: bool,
    ) -> tuple[object, ...]:
        import asyncio

        from qy.errors import QyAggregateError
        from qy.errors import QyError

        async def run_thunk(idx: int) -> object:
            thunk = BytecodeFunctionValue(self.program.functions[idx], env, self.program)
            return (await self._run_function(thunk, ())).value

        tasks = [asyncio.create_task(run_thunk(i)) for i in thunk_indices]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        if aggregate_errors:
            errors = tuple(
                r if isinstance(r, QyError) else QyRuntimeError(str(r), span=None, cause=r)
                for r in raw
                if isinstance(r, BaseException)
            )
            if errors:
                raise QyAggregateError(
                    f"parallel failed with {len(errors)} error(s)", errors=errors
                )
        else:
            for r in raw:
                if isinstance(r, BaseException):
                    raise r
        return tuple(raw)

    async def _race_first(
        self,
        thunk_indices: list[int],
        env: Environment,
    ) -> object:
        import asyncio

        async def run_thunk(idx: int) -> object:
            thunk = BytecodeFunctionValue(self.program.functions[idx], env, self.program)
            return (await self._run_function(thunk, ())).value

        tasks = [asyncio.create_task(run_thunk(i)) for i in thunk_indices]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        return next(iter(done)).result()

    async def _cache_eval(self, cache_key: object, thunk_idx: int, env: Environment) -> object:
        import asyncio

        try:
            cached = env.cache_lookup(cache_key)
            return await _await_if_needed(cached)
        except KeyError:
            pass

        thunk = BytecodeFunctionValue(self.program.functions[thunk_idx], env, self.program)

        async def run_thunk() -> object:
            return (await self._run_function(thunk, ())).value

        task: asyncio.Task[object] = asyncio.create_task(run_thunk())
        env.cache_define(cache_key, task)
        try:
            result = await task
        except Exception:
            env.cache_discard(cache_key)
            raise
        env.cache_define(cache_key, result)
        return result

    async def _define_module(
        self,
        module_name: Symbol,
        function_index: int,
        env: Environment,
        *,
        export_names: tuple[Symbol, ...] = (),
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

        all_bindings = {
            sym: value for sym, value in module_env.local_bindings().items() if sym not in baseline
        }

        if export_names:
            selected: dict[Symbol, object] = {}
            for name in export_names:
                if name in all_bindings:
                    selected[name] = all_bindings[name]
        else:
            selected = all_bindings

        runtime_exports: dict[Symbol, object] = {}
        macro_exports: dict[Symbol, object] = {}
        for sym, value in selected.items():
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
        return env.define_once(module_name, module)

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
                    env.define_once(spec.alias, module.resolve(spec.name))
                elif spec.name not in module.macro_exports:
                    raise KeyError(f"module {module_name.name!r} has no export {spec.name.name!r}")
        except (KeyError, ValueError) as e:
            raise EvaluationError(str(e)) from e

    async def _defeffect(self, name: Symbol, resumable: bool, env: Environment) -> None:
        env.define_once(name, EffectDefinition(name, resumable))

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

        # Capture current frame state into an EffectFrame structure.
        # This explicit representation clarifies what must be saved for resumption.
        effect_frame = _EffectFrame(
            registers=tuple(frame.registers),
            env=frame.env,
            pc=frame.pc,
            parents=tuple(frame.parents),
            results=tuple(frame.results),
            function_value=frame.function_value,
            function=frame.function,
        )

        vm = self

        async def resume(value: object) -> object:
            # Restore the captured frame state and continue execution.
            resume_registers = list(effect_frame.registers)
            resume_registers[dest_reg] = value
            resume_frame = _Frame(
                effect_frame.function_value,
                effect_frame.function,
                effect_frame.pc,
                resume_registers,
                effect_frame.env,
                list(effect_frame.parents),
                list(effect_frame.results),
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
        if not isinstance(continuation, QyContinuation):
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


async def call_function_value(
    function_value: BytecodeFunctionValue,
    args: tuple[object, ...],
    env: Environment,
) -> object:
    if function_value.program is None:
        raise QyRuntimeError(
            "cannot call BytecodeFunctionValue without program context",
            span=None,
        )
    vm = RegisterVirtualMachine(function_value.program, env)
    result = await vm._run_function(function_value, args)
    return result.value


def _raise_for_diagnostics(program: BytecodeProgram) -> None:
    diagnostics = tuple(item for item in program.diagnostics if item.severity == "error")
    if not diagnostics:
        return
    messages = "; ".join(item.message for item in diagnostics)
    raise QyRuntimeError(f"cannot execute bytecode with diagnostics: {messages}")


def _sequence_to_args(value: object) -> tuple[object, ...]:
    from qy.literals import default_literal_type
    from qy.literals import try_default_literal
    from qy.values import QyCons
    from qy.values import QyEmptyChain
    from qy.values import QyEmptyList

    def _normalize_arg(item: object) -> object:
        if isinstance(item, Symbol) and default_literal_type(item) is not None:
            return try_default_literal(item)
        return item

    if isinstance(value, (list, tuple)):
        return tuple(_normalize_arg(item) for item in value)
    if isinstance(value, QyEmptyChain | QyEmptyList):
        return ()
    if isinstance(value, QyCons):
        result: list[object] = []
        node: object = value
        while isinstance(node, QyCons):
            result.append(_normalize_arg(node.head))
            node = node.tail
        return tuple(result)
    return (_normalize_arg(value),)


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
