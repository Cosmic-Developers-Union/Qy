# coding: utf-8

from __future__ import annotations

from qy.core.operators import EffectOperator
from qy.display import format_value
from qy.errors import EvaluationError
from qy.frontend.reader import Symbol
from qy.import_.module import StandardModule
from qy.session.runtime_space import RuntimeSpace as Environment


def module() -> StandardModule:
    print_operator = EffectOperator("print", _print, "打印求值后的值，并返回最后一个打印值。")
    return StandardModule(
        "qy.io",
        {
            Symbol("print"): print_operator,
            Symbol("echo"): EffectOperator(
                "echo", _print, "print 的别名；打印值并返回最后一个值。"
            ),
        },
    )


async def _print(args: tuple[object, ...], env: Environment) -> object:
    # EffectOperator 是 raw-argument 算子：字面量实参以 syntax datum（Symbol）
    # 形式到达这里，而复合实参已由 VM 求值完成（Chain / NumberValue ...）。
    # 因此只解析仍是 Symbol 的字面量，绝不重新求值已求好的 runtime value
    # ——否则 cons 结果会被误当作调用执行。
    values = tuple(_resolve_literal(arg, env) for arg in args)
    print(" ".join(format_value(value) for value in values))
    if not values:
        return None
    return values[-1]


def _resolve_literal(value: object, env: Environment) -> object:
    if isinstance(value, Symbol):
        # Only literal spellings (numbers, strings, chars, true/false/nil/T/none)
        # are resolved here. An arbitrary quoted symbol such as `(print 'chain)`
        # must stay a symbol even if its name is bound in the symbol-space chain.
        from qy.session.pre_ss import default_literal_type

        if default_literal_type(value) is None:
            return value
        try:
            return env.resolve(value)
        except EvaluationError:
            return value
    return value
