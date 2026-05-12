# coding: utf-8

from __future__ import annotations

import inspect
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from typing import cast

from qy.errors import EvaluationError
from qy.errors import QyArityError
from qy.errors import QyEffectSignal
from qy.errors import QyRuntimeError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.evaluator import ComponentDefinition
from qy.evaluator import ControlOperator
from qy.evaluator import EffectDefinition
from qy.evaluator import EffectOperator
from qy.evaluator import Environment
from qy.evaluator import MacroDefinition
from qy.evaluator import MetaOperator
from qy.evaluator import PureOperator
from qy.evaluator import QyContinuation
from qy.evaluator import ScopeOperator
from qy.evaluator import UserFunction
from qy.evaluator import run_async
from qy.evaluator import standard_environment
from qy.ir import AssertExpr
from qy.ir import CallExpr
from qy.ir import ComponentExpr
from qy.ir import CondExpr
from qy.ir import DefeffectExpr
from qy.ir import DefunExpr
from qy.ir import EffectHandler
from qy.ir import FromImportExpr
from qy.ir import HandleExpr
from qy.ir import IRExpr
from qy.ir import LambdaExpr
from qy.ir import LetExpr
from qy.ir import LiteralExpr
from qy.ir import MacroExpr
from qy.ir import ModuleExpr
from qy.ir import PerformExpr
from qy.ir import ProgramIR
from qy.ir import QuoteExpr
from qy.ir import ResumeExpr
from qy.ir import RuntimeEvalExpr
from qy.ir import RuntimeMetaCallExpr
from qy.ir import SymbolRefExpr
from qy.ir import UnresolvedSymbolExpr
from qy.operator_runtime import operator_uses_raw_args
from qy.operator_runtime import validate_operator_arity
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import Symbol
from qy.stdlib import load_module_async
from qy.stdlib import register_module
from qy.stdlib.module import StandardModule
from qy.values import QY_NIL
from qy.values import QyCons
from qy.values import list_to_qy_cons
from qy.values import qy_cons_to_tuple

__all__ = [
    "IRCallableKind",
    "IRFunction",
    "IRVirtualMachine",
    "evaluate_ir",
    "evaluate_ir_async",
    "evaluate_ir_source",
    "evaluate_ir_source_async",
]

IRCallableKind = Literal["function", "component", "lambda"]


@dataclass(frozen=True, slots=True)
class IRFunction:
    name: Symbol
    params: tuple[Symbol, ...]
    body: tuple[IRExpr, ...]
    closure: Environment
    kind: IRCallableKind = "function"

    async def __call__(self, *args: object) -> object:
        return await IRVirtualMachine(self.closure)._apply_ir_function(self, args)


@dataclass(frozen=True, slots=True)
class _TailCall:
    function: IRFunction
    args: tuple[object, ...]


class IRVirtualMachine:
    def __init__(self, env: Environment | None = None) -> None:
        self.env = env or standard_environment()

    async def evaluate_program(self, program: ProgramIR) -> list[object]:
        _raise_for_diagnostics(program)
        results: list[object] = []
        self._bind_callable_definitions(program.body, self.env)
        for expression in program.body:
            results.append(await self.evaluate(expression, self.env))
        return results

    async def evaluate(self, expression: IRExpr, env: Environment | None = None) -> object:
        return await self._eval(expression, env or self.env, current_function=None)

    async def _eval(
        self,
        expression: IRExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if isinstance(expression, LiteralExpr):
            return expression.value
        if isinstance(expression, SymbolRefExpr):
            return env.resolve(expression.symbol)
        if isinstance(expression, UnresolvedSymbolExpr):
            return env.resolve(expression.symbol)
        if isinstance(expression, QuoteExpr):
            return _quote_data(expression.form)
        if isinstance(expression, RuntimeEvalExpr):
            form = await self._eval(expression.expression, env, current_function=current_function)
            return await self._evaluate_runtime_form(form, env)
        if isinstance(expression, RuntimeMetaCallExpr):
            return await self._eval_runtime_meta_call(expression, env)
        if isinstance(expression, CallExpr):
            return await self._eval_call(expression, env, current_function=current_function)
        if isinstance(expression, LetExpr):
            return await self._eval_let(expression, env, current_function=current_function)
        if isinstance(expression, LambdaExpr):
            return IRFunction(Symbol("<lambda>"), expression.params, expression.body, env, "lambda")
        if isinstance(expression, DefunExpr):
            function = IRFunction(expression.name, expression.params, expression.body, env)
            return env.define(expression.name, function)
        if isinstance(expression, ComponentExpr):
            component = IRFunction(
                expression.name,
                expression.params,
                expression.body,
                env,
                "component",
            )
            return env.define(expression.name, component)
        if isinstance(expression, MacroExpr):
            macro = MacroDefinition(
                expression.name,
                expression.params,
                expression.raw_body,
                env,
            )
            return env.define(expression.name, macro)
        if isinstance(expression, DefeffectExpr):
            effect = EffectDefinition(expression.name, expression.resumable)
            return env.define(expression.name, effect)
        if isinstance(expression, CondExpr):
            return await self._eval_cond(expression, env, current_function=current_function)
        if isinstance(expression, FromImportExpr):
            return await self._eval_from_import(expression, env)
        if isinstance(expression, ModuleExpr):
            return await self._eval_module(expression, env)
        if isinstance(expression, PerformExpr):
            return await self._eval_perform(expression, env, current_function=current_function)
        if isinstance(expression, HandleExpr):
            return await self._eval_handle(expression, env, current_function=current_function)
        if isinstance(expression, ResumeExpr):
            return await self._eval_resume(expression, env, current_function=current_function)
        if isinstance(expression, AssertExpr):
            return await self._eval_assert(expression, env, current_function=current_function)
        raise QyRuntimeError(f"unsupported IR expression {expression!r}")

    async def _eval_body(
        self,
        body: tuple[IRExpr, ...],
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if not body:
            raise QyArityError("body must contain at least one expression")

        self._bind_callable_definitions(body, env)
        return await self._eval_body_from(body, 0, env, current_function=current_function)

    async def _eval_body_from(
        self,
        body: tuple[IRExpr, ...],
        index: int,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        result: object = None
        for current in range(index, len(body)):
            try:
                result = await self._eval(
                    body[current],
                    env,
                    current_function=current_function,
                )
            except QyEffectSignal as e:
                self._compose_effect_continuation(
                    e,
                    lambda resumed, next_index=current + 1: self._continue_body_after_resume(
                        body,
                        next_index,
                        resumed,
                        env,
                        current_function=current_function,
                    ),
                )
                raise
            if isinstance(result, _TailCall):
                return result
        return result

    async def _continue_body_after_resume(
        self,
        body: tuple[IRExpr, ...],
        index: int,
        resumed: object,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if index >= len(body):
            return resumed
        return await self._eval_body_from(body, index, env, current_function=current_function)

    async def _eval_call(
        self,
        expression: CallExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        try:
            operator = await self._eval(
                expression.operator,
                env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed_operator: self._eval_call_arguments(
                    expression,
                    resumed_operator,
                    0,
                    (),
                    env,
                    current_function=current_function,
                ),
            )
            raise
        if operator_uses_raw_args(operator):
            return await self._finish_call(
                expression,
                operator,
                (),
                env,
                current_function=current_function,
            )
        return await self._eval_call_arguments(
            expression,
            operator,
            0,
            (),
            env,
            current_function=current_function,
        )

    async def _eval_call_arguments(
        self,
        expression: CallExpr,
        operator: object,
        index: int,
        values: tuple[object, ...],
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if index >= len(expression.args):
            return await self._finish_call(
                expression,
                operator,
                values,
                env,
                current_function=current_function,
            )
        try:
            value = await self._eval(
                expression.args[index],
                env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed: self._eval_call_arguments(
                    expression,
                    operator,
                    index + 1,
                    (*values, resumed),
                    env,
                    current_function=current_function,
                ),
            )
            raise
        return await self._eval_call_arguments(
            expression,
            operator,
            index + 1,
            (*values, value),
            env,
            current_function=current_function,
        )

    async def _finish_call(
        self,
        expression: CallExpr,
        operator: object,
        args: tuple[object, ...],
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if (
            expression.tail_position
            and current_function is not None
            and isinstance(operator, IRFunction)
        ):
            return _TailCall(operator, args)
        validate_operator_arity(operator, len(expression.raw_args), span=expression.span)
        return await self._apply_operator(operator, args, expression, env)

    async def _eval_let(
        self,
        expression: LetExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        local_env = env.child()
        return await self._eval_let_bindings(
            expression,
            0,
            local_env,
            current_function=current_function,
        )

    async def _eval_let_bindings(
        self,
        expression: LetExpr,
        index: int,
        local_env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if index >= len(expression.bindings):
            return await self._eval_body(
                expression.body,
                local_env,
                current_function=current_function,
            )
        binding = expression.bindings[index]
        try:
            value = await self._eval(
                binding.value,
                local_env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed: self._continue_let_after_binding_resume(
                    expression,
                    index,
                    resumed,
                    local_env,
                    current_function=current_function,
                ),
            )
            raise
        local_env.define(binding.symbol, value)
        return await self._eval_let_bindings(
            expression,
            index + 1,
            local_env,
            current_function=current_function,
        )

    async def _continue_let_after_binding_resume(
        self,
        expression: LetExpr,
        index: int,
        resumed: object,
        local_env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        binding = expression.bindings[index]
        local_env.define(binding.symbol, resumed)
        return await self._eval_let_bindings(
            expression,
            index + 1,
            local_env,
            current_function=current_function,
        )

    async def _eval_cond(
        self,
        expression: CondExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        return await self._eval_cond_from(
            expression,
            0,
            env,
            current_function=current_function,
        )

    async def _eval_cond_from(
        self,
        expression: CondExpr,
        index: int,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if index >= len(expression.clauses):
            return None
        clause = expression.clauses[index]
        try:
            condition = await self._eval(
                clause.condition,
                env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed: self._finish_cond_condition(
                    expression,
                    index,
                    resumed,
                    env,
                    current_function=current_function,
                ),
            )
            raise
        return await self._finish_cond_condition(
            expression,
            index,
            condition,
            env,
            current_function=current_function,
        )

    async def _finish_cond_condition(
        self,
        expression: CondExpr,
        index: int,
        condition: object,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if _truthy(condition):
            return await self._eval(
                expression.clauses[index].result,
                env,
                current_function=current_function,
            )
        return await self._eval_cond_from(
            expression,
            index + 1,
            env,
            current_function=current_function,
        )

    async def _eval_assert(
        self,
        expression: AssertExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        try:
            condition = await self._eval(
                expression.condition,
                env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed: self._finish_assert(
                    expression,
                    resumed,
                    env,
                    current_function=current_function,
                ),
            )
            raise
        return await self._finish_assert(
            expression,
            condition,
            env,
            current_function=current_function,
        )

    async def _finish_assert(
        self,
        expression: AssertExpr,
        condition: object,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if _truthy(condition):
            return condition

        if expression.message is None:
            message: object = Symbol("assertion failed")
        else:
            try:
                message = await self._eval(
                    expression.message,
                    env,
                    current_function=current_function,
                )
            except QyEffectSignal as e:
                self._compose_effect_continuation(
                    e,
                    lambda resumed: self._raise_assert_failed(
                        expression,
                        resumed,
                        condition,
                    ),
                )
                raise
        return await self._raise_assert_failed(expression, message, condition)

    async def _raise_assert_failed(
        self,
        expression: AssertExpr,
        message: object,
        condition: object,
    ) -> object:
        raise QyEffectSignal(
            "assert-failed",
            message,
            _identity_continuation("assert-failed", False),
            resumable=False,
            span=expression.span,
            metadata={"condition": condition},
        )

    async def _eval_perform(
        self,
        expression: PerformExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        definition = self._resolve_effect_definition(
            expression.effect.name,
            env,
            expression.span,
        )
        try:
            argument = await self._eval(
                expression.argument,
                env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed: self._raise_effect_signal(
                    expression.effect.name,
                    resumed,
                    definition.resumable,
                    expression.span,
                ),
            )
            raise
        return await self._raise_effect_signal(
            expression.effect.name,
            argument,
            definition.resumable,
            expression.span,
        )

    async def _eval_handle(
        self,
        expression: HandleExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        handlers = {handler.effect.name: handler for handler in expression.handlers}
        try:
            return await self._eval(
                expression.expression,
                env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            return await self._handle_effect_signal(
                e,
                handlers,
                env,
                current_function=current_function,
            )

    async def _handle_effect_signal(
        self,
        signal: QyEffectSignal,
        handlers: Mapping[str, EffectHandler],
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        try:
            handler = handlers[signal.effect]
        except KeyError:
            raise signal from None
        local_env = env.child(
            {
                handler.arg_name: signal.arg,
                handler.continuation_name: signal.continuation,
            }
        )
        try:
            return await self._eval_body(
                handler.body,
                local_env,
                current_function=current_function,
            )
        except QyEffectSignal as nested:
            return await self._handle_effect_signal(
                nested,
                handlers,
                env,
                current_function=current_function,
            )

    async def _eval_resume(
        self,
        expression: ResumeExpr,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        try:
            continuation = await self._eval(
                expression.continuation,
                env,
                current_function=current_function,
            )
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed: self._finish_resume_continuation(
                    expression,
                    resumed,
                    env,
                    current_function=current_function,
                ),
            )
            raise
        return await self._finish_resume_continuation(
            expression,
            continuation,
            env,
            current_function=current_function,
        )

    async def _finish_resume_continuation(
        self,
        expression: ResumeExpr,
        continuation: object,
        env: Environment,
        *,
        current_function: IRFunction | None,
    ) -> object:
        if not isinstance(continuation, QyContinuation):
            raise QyTypeError(
                f"resume expects a continuation, got {continuation!r}",
                span=expression.span,
                metadata={"value": continuation},
            )
        try:
            value = await self._eval(expression.value, env, current_function=current_function)
        except QyEffectSignal as e:
            self._compose_effect_continuation(
                e,
                lambda resumed: continuation.resume(resumed),
            )
            raise
        return await continuation.resume(value)

    async def _eval_from_import(self, expression: FromImportExpr, env: Environment) -> object:
        try:
            module = await load_module_async(expression.module.name)
            for spec in expression.specs:
                env.define(spec.alias, module.resolve(spec.name))
        except (KeyError, ValueError) as e:
            raise EvaluationError(str(e), span=expression.span) from e
        return None

    async def _eval_module(self, expression: ModuleExpr, env: Environment) -> object:
        module_env = env.child()
        baseline = set(module_env.local_bindings())
        await self._eval_body(expression.body, module_env, current_function=None)
        exports = {
            symbol: value
            for symbol, value in module_env.local_bindings().items()
            if symbol not in baseline
        }
        module = StandardModule(expression.name.name, exports)
        register_module(module)
        return env.define(expression.name, module)

    async def _eval_runtime_meta_call(
        self,
        expression: RuntimeMetaCallExpr,
        env: Environment,
    ) -> object:
        operator = env.resolve(expression.operator.symbol)
        if isinstance(operator, MetaOperator):
            return await _await_if_needed(operator(expression.raw_form, env))
        if isinstance(operator, MacroDefinition):
            expanded = await operator.expand(tuple(expression.raw_form[1:]))
            return await self._evaluate_runtime_form(expanded, env)
        raise QyTypeError(
            f"{expression.operator.symbol.name!r} is not a runtime meta operator",
            span=expression.span,
            metadata={"operator": operator},
        )

    async def _evaluate_runtime_form(self, form: object, env: Environment) -> object:
        if isinstance(form, QyCons):
            form = qy_cons_to_tuple(form)
        if isinstance(form, Symbol | tuple):
            from qy.lowering import lower

            program = lower([cast(Form, form)], env)
            results = await self.evaluate_program(program)
            return None if not results else results[-1]
        return form

    async def _apply_operator(
        self,
        operator: object,
        args: tuple[object, ...],
        expression: CallExpr,
        env: Environment,
    ) -> object:
        try:
            if isinstance(operator, IRFunction):
                return await self._apply_ir_function(operator, args)
            if isinstance(operator, MetaOperator):
                return await _await_if_needed(
                    operator((_raw_operator_expression(expression), *expression.raw_args), env)
                )
            if isinstance(operator, ScopeOperator | ControlOperator | EffectOperator):
                return await _await_if_needed(operator(expression.raw_args, env))
            if isinstance(operator, MacroDefinition):
                expanded = await operator.expand(expression.raw_args)
                return await self._evaluate_runtime_form(expanded, env)
            if isinstance(operator, PureOperator):
                if operator.argument_evaluator is not None:
                    evaluated_args = await _await_if_needed(
                        operator.argument_evaluator(expression.raw_args, env)
                    )
                    if not isinstance(evaluated_args, tuple):
                        raise QyTypeError(
                            f"{operator.name} argument evaluator must return a tuple, "
                            f"got {evaluated_args!r}",
                            span=expression.span,
                            metadata={"operator": operator.name, "value": evaluated_args},
                        )
                    return await _await_if_needed(operator(*evaluated_args))
                return await _await_if_needed(operator(*args))
            if isinstance(operator, UserFunction | ComponentDefinition):
                return await _await_if_needed(operator(*args))
            raise QyTypeError(
                f"IR call resolved to non-callable {operator!r}",
                span=expression.span,
                metadata={"operator": operator},
            )
        except (EvaluationError, QyEffectSignal):
            raise
        except Exception as e:
            raise QyRuntimeError(
                str(e),
                span=expression.span,
                cause=e,
                metadata={"python_exception": type(e).__name__},
            ) from e

    async def _apply_ir_function(
        self,
        function: IRFunction,
        args: tuple[object, ...],
    ) -> object:
        current_function = function
        current_args = args
        while True:
            if len(current_args) != len(current_function.params):
                raise QyArityError(
                    f"{current_function.name.name} expects "
                    f"{len(current_function.params)} arguments, got {len(current_args)}",
                    span=current_function.name.span,
                    metadata={
                        "expected": len(current_function.params),
                        "actual": len(current_args),
                        "function": current_function.name.name,
                    },
                )

            local_env = current_function.closure.child(
                dict(zip(current_function.params, current_args, strict=True))
            )
            result = await self._eval_body(
                current_function.body,
                local_env,
                current_function=current_function,
            )
            if not isinstance(result, _TailCall):
                return result
            current_function = result.function
            current_args = result.args

    def _bind_callable_definitions(self, body: tuple[IRExpr, ...], env: Environment) -> None:
        for expression in body:
            if isinstance(expression, DefunExpr):
                env.define(
                    expression.name,
                    IRFunction(expression.name, expression.params, expression.body, env),
                )
            elif isinstance(expression, ComponentExpr):
                env.define(
                    expression.name,
                    IRFunction(
                        expression.name,
                        expression.params,
                        expression.body,
                        env,
                        "component",
                    ),
                )

    async def _raise_effect_signal(
        self,
        effect_name: str,
        argument: object,
        resumable: bool,
        span: SourceSpan | None,
    ) -> object:
        raise QyEffectSignal(
            effect_name,
            argument,
            _identity_continuation(effect_name, resumable),
            resumable=resumable,
            span=span,
        )

    def _resolve_effect_definition(
        self,
        effect_name: str,
        env: Environment,
        span: SourceSpan | None,
    ) -> EffectDefinition:
        try:
            value = env.resolve(Symbol(effect_name))
        except EvaluationError as e:
            raise EvaluationError(
                f"effect {effect_name!r} is not declared; use defeffect before perform",
                span=span,
                cause=e,
                metadata={"effect": effect_name},
            ) from e
        if not isinstance(value, EffectDefinition):
            raise QyTypeError(
                f"{effect_name!r} is not an effect definition",
                span=span,
                metadata={"effect": effect_name, "value": value},
            )
        return value

    def _compose_effect_continuation(
        self,
        signal: QyEffectSignal,
        then: Callable[[object], object],
    ) -> None:
        previous = signal.continuation
        if not isinstance(previous, QyContinuation):
            return

        async def resume(value: object) -> object:
            previous_result = await previous.resume(value)
            return await _await_if_needed(then(previous_result))

        signal.continuation = QyContinuation(signal.effect, previous.resumable, resume)


def evaluate_ir(program: ProgramIR, env: Environment | None = None) -> object:
    return run_async(evaluate_ir_async(program, env))


async def evaluate_ir_async(program: ProgramIR, env: Environment | None = None) -> object:
    results = await IRVirtualMachine(env).evaluate_program(program)
    return None if not results else results[-1]


def evaluate_ir_source(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> object:
    return run_async(evaluate_ir_source_async(source, env, source_name=source_name))


async def evaluate_ir_source_async(
    source: str,
    env: Environment | None = None,
    *,
    source_name: str | None = None,
) -> object:
    from qy.lowering import lower
    from qy.macroexpand import macroexpand_source_async

    runtime_env = env or standard_environment()
    expansion = await macroexpand_source_async(source, runtime_env, source_name=source_name)
    errors = tuple(item for item in expansion.diagnostics if item.severity == "error")
    if errors:
        messages = "; ".join(item.message for item in errors)
        raise QyRuntimeError(f"cannot execute macroexpanded source: {messages}")
    return await evaluate_ir_async(
        lower(expansion.forms, runtime_env),
        runtime_env,
    )


def _raise_for_diagnostics(program: ProgramIR) -> None:
    diagnostics = tuple(item for item in program.diagnostics if item.severity == "error")
    if not diagnostics:
        return
    messages = "; ".join(item.message for item in diagnostics)
    raise QyRuntimeError(f"cannot execute IR with diagnostics: {messages}")


def _quote_data(value: object) -> object:
    if isinstance(value, DottedTuple):
        return list_to_qy_cons((_quote_data(item) for item in value), _quote_data(value.tail))
    if isinstance(value, tuple):
        return list_to_qy_cons(_quote_data(item) for item in value)
    return value


def _truthy(value: object) -> bool:
    return value is not False and value is not None and value is not QY_NIL and value != ()


def _raw_operator_expression(expression: CallExpr) -> object:
    if isinstance(expression.operator, SymbolRefExpr):
        return expression.operator.symbol
    return expression.operator


async def _await_if_needed(value: object) -> object:
    if inspect.iscoroutine(value):
        return await value
    return value


def _identity_continuation(effect_name: str, resumable: bool) -> QyContinuation:
    async def resume(value: object) -> object:
        return value

    return QyContinuation(effect_name, resumable, resume)
