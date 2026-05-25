# coding: utf-8
# QY_MIGRATION_TARGET: migrated from qy/register_vm.py

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from qy.backend.vm.bytecode import BytecodeFunction
from qy.backend.vm.bytecode import BytecodeProgram
from qy.backend.vm.bytecode import Instruction
from qy.backend.vm.bytecode import Register
from qy.core.operator_runtime import runtime_operator_semantics
from qy.core.operator_runtime import validate_operator_arity
from qy.core.operators import PureOperator
from qy.core.syntax import nil as QY_NIL
from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.frontend.reader import Symbol
from qy.sem.runtime import EffectDefinition
from qy.session.runtime_space import RuntimeSpace as Environment
from qy.session.runtime_space import create_standard_runtime_space as standard_environment
from qy.vm.bytecode import BytecodeFunctionValue
from qy.vm.instance.frame import QyContinuation
from qy.vm.instance.frame import VirtualStackFrame
from qy.vm.instance.state import VirtualStack

__all__ = [
    "RegisterVirtualMachine",
    "call_function_value",
    "evaluate_bytecode",
    "evaluate_bytecode_async",
    "evaluate_bytecode_source",
    "evaluate_bytecode_source_async",
    "evaluate_form_async",
    "evaluate_form_body_async",
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
                callee = frame.registers[_register(callee_register)]
                if isinstance(callee, PureOperator) and callee.name == "/" and len(args) >= 2:
                    for divisor in args[1:]:
                        if isinstance(divisor, bool):
                            continue
                        if isinstance(divisor, int | float) and divisor == 0:
                            saved_registers = tuple(frame.registers)
                            saved_env = frame.env
                            saved_pc = frame.pc

                            async def _resume_div_by_zero(
                                value: object,
                                _saved_regs=saved_registers,
                                _saved_env=saved_env,
                                _saved_pc=saved_pc,
                            ) -> object:
                                regs = list(_saved_regs)
                                regs[_register(dest)] = value
                                resume_frame = _Frame(
                                    frame.function_value,
                                    frame.function,
                                    _saved_pc,
                                    regs,
                                    _saved_env,
                                    list(frame.parents),
                                    list(frame.results),
                                )
                                while resume_frame.pc < len(resume_frame.function.instructions):
                                    inst = resume_frame.function.instructions[resume_frame.pc]
                                    resume_frame.pc += 1
                                    result = await self._execute_instruction(resume_frame, inst)
                                    if isinstance(result, _FrameResult):
                                        return result.value
                                    if isinstance(result, _Frame):
                                        resume_frame = result
                                return None

                            continuation = QyContinuation(
                                "divide-by-zero", True, _resume_div_by_zero
                            )
                            raise QyEffectSignal(
                                "divide-by-zero",
                                0,
                                continuation,
                                resumable=True,
                                span=instruction.span,
                            )
                frame.registers[_register(dest)] = await self._call(
                    callee,
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

        from qy.core.syntax import Chain
        from qy.core.syntax import Chain as QyCons
        from qy.core.syntax import chain_to_tuple as qy_cons_to_tuple
        from qy.frontend.reader import Form
        from qy.frontend.reader import Symbol as _Symbol
        from qy.passes.build import bytecode_artifact
        from qy.passes.build import compile_core_forms_to_bytecode_async
        from qy.passes.pass_base import PipelineSession

        if isinstance(form, QyCons):
            form = qy_cons_to_tuple(form)
        if not isinstance(form, _Symbol | tuple | Chain):
            return form
        session = PipelineSession(env=env)
        result = await compile_core_forms_to_bytecode_async(
            [cast(Form, form)],
            session,
        )
        bytecode = bytecode_artifact(result)
        sub_vm = RegisterVirtualMachine(bytecode, env)
        outcome = await sub_vm.evaluate_program()
        return None if not outcome else outcome[-1]

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
        for t in pending:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        winner = next(iter(done))
        exc = winner.exception()
        if exc is not None:
            for t in done:
                if t is not winner:
                    t.exception()  # mark as retrieved
            raise exc
        for t in done:
            if t is not winner:
                try:
                    t.exception()  # mark as retrieved
                except Exception:
                    pass
        return winner.result()

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
        from qy.import_.loader import cache_source_module
        from qy.import_.loader import lookup_source_module
        from qy.macro import MacroDefinition
        from qy.std import register_module
        from qy.std.module import StandardModule

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
        from qy.std import load_module_async
        from qy.std.imports import ImportSpec

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
                    resume_frame = result
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
            return await self._dispatch_effect(e, handler_specs, env)

    async def _dispatch_effect(
        self,
        signal: QyEffectSignal,
        handler_specs: tuple[object, ...],
        env: Environment,
    ) -> object:
        """匹配并执行 handler, 并在 handler resume 时保持 handler 活跃."""
        handler_fn = None
        for spec in handler_specs:
            if not isinstance(spec, tuple) or len(spec) != 2:
                continue
            effect_sym, handler_fn_idx = spec
            if not isinstance(effect_sym, Symbol) or not isinstance(handler_fn_idx, int):
                continue
            if effect_sym.name == signal.effect:
                handler_fn = BytecodeFunctionValue(self.program.functions[handler_fn_idx], env)
                break
        if handler_fn is None:
            raise signal

        arg = signal.arg
        continuation = signal.continuation
        while True:
            try:
                handler_result = await self._run_function(handler_fn, (arg, continuation))
                result_value = handler_result.value
                if isinstance(result_value, QyContinuation):
                    if not result_value.resumable:
                        return result_value
                    continuation = result_value
                    arg = None
                else:
                    return result_value
            except QyEffectSignal as nested:
                # handler resume 中产生的新 effect, 重新 dispatch
                signal = nested
                handler_fn_new = None
                for spec in handler_specs:
                    if not isinstance(spec, tuple) or len(spec) != 2:
                        continue
                    effect_sym, handler_fn_idx = spec
                    if not isinstance(effect_sym, Symbol) or not isinstance(handler_fn_idx, int):
                        continue
                    if effect_sym.name == nested.effect:
                        handler_fn_new = BytecodeFunctionValue(
                            self.program.functions[handler_fn_idx], env
                        )
                        break
                if handler_fn_new is None:
                    raise
                handler_fn = handler_fn_new
                arg = nested.arg
                continuation = nested.continuation

    async def _resume(self, continuation: object, value: object) -> object:
        if not isinstance(continuation, QyContinuation):
            raise QyRuntimeError(
                f"resume expects a continuation, got {continuation!r}",
                metadata={"value": continuation},
            )
        return await continuation.resume(value)


def evaluate_bytecode(program: BytecodeProgram, env: Environment | None = None) -> object:
    from qy.async_utils import run_coro

    return run_coro(evaluate_bytecode_async(program, env))


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
    from qy.async_utils import run_coro

    return run_coro(evaluate_bytecode_source_async(source, env, source_name=source_name))


async def evaluate_bytecode_source_async(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> object:
    from qy.passes.build import bytecode_artifact
    from qy.passes.build import compile_source_to_bytecode_async
    from qy.passes.pass_base import PipelineSession

    runtime_env = env or standard_environment()
    session = PipelineSession(env=runtime_env, source_name=source_name)
    result = await compile_source_to_bytecode_async(source, session)
    bytecode = bytecode_artifact(result)
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


async def evaluate_form_async(expression: object, env: Environment) -> object:
    """Evaluate a single expression through the pipeline.

    Symbol resolution short-circuits via env.resolve. Otherwise routes through
    the unified pipeline (frontend.surface_normalize → macro.expand → ... → emit.bytecode).
    """
    from typing import cast

    from qy.frontend.reader import Form
    from qy.passes.build import bytecode_artifact
    from qy.passes.build import compile_forms_to_bytecode_async
    from qy.passes.pass_base import PipelineSession

    if isinstance(expression, Symbol):
        return env.resolve(expression)

    session = PipelineSession(env=env)
    result = await compile_forms_to_bytecode_async([cast(Form, expression)], session)
    bytecode = bytecode_artifact(result)
    vm = RegisterVirtualMachine(bytecode, env)
    results = await vm.evaluate_program()
    return None if not results else results[-1]


async def evaluate_form_body_async(body: tuple[object, ...], env: Environment) -> object:
    """Evaluate a sequence of expressions, returning the last result.

    Supports effect handling by composing continuations across sequential
    expressions.
    """
    from qy.vm.instance.frame import QyContinuation

    if not body:
        raise QyArityError("body must contain at least one expression")

    async def _body_from(index: int) -> object:
        result = None
        for current in range(index, len(body)):
            try:
                result = await evaluate_form_async(body[current], env)
            except QyEffectSignal as e:
                _compose(e, current + 1)
                raise
        return result

    def _compose(signal: QyEffectSignal, next_index: int) -> None:
        previous = signal.continuation
        if not isinstance(previous, QyContinuation):
            return

        async def resume(value: object) -> object:
            previous_result = await previous.resume(value)
            if next_index >= len(body):
                return previous_result
            return await _body_from(next_index)

        signal.continuation = QyContinuation(signal.effect, previous.resumable, resume)

    return await _body_from(0)


def _raise_for_diagnostics(program: BytecodeProgram) -> None:
    diagnostics = tuple(item for item in program.diagnostics if item.severity == "error")
    if not diagnostics:
        return
    messages = "; ".join(item.message for item in diagnostics)
    raise QyRuntimeError(f"cannot execute bytecode with diagnostics: {messages}")


def _sequence_to_args(value: object) -> tuple[object, ...]:
    from qy.core.syntax import Chain
    from qy.core.syntax import Chain as QyCons
    from qy.core.syntax import QyNil as QyEmptyChain
    from qy.core.syntax import QyNil as QyEmptyList
    from qy.core.syntax import chain_to_list
    from qy.core.syntax import is_chain
    from qy.session.pre_ss import default_literal_type
    from qy.session.pre_ss import try_default_literal

    def _normalize_arg(item: object) -> object:
        if isinstance(item, Symbol) and default_literal_type(item) is not None:
            return try_default_literal(item)
        return item

    if isinstance(value, (list, tuple)):
        return tuple(_normalize_arg(item) for item in value)
    if isinstance(value, QyEmptyChain | QyEmptyList):
        return ()
    if isinstance(value, Chain) or is_chain(value):
        items = chain_to_list(value)
        return tuple(_normalize_arg(item) for item in items)
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
    """nil-only truthiness: only QY_NIL is false.

    This is the language-core truth model used by cond/JUMP_IF_FALSE.
    The standard-profile ``truthy`` operator provides complex truthiness.
    """
    return value is not QY_NIL


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
