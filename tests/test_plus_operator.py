"""测试 + 算子在新语义下的行为。.

新设计（与 LANGUAGE.md 对齐）：

- ``+`` 接受同一 concrete ``NumberValue`` 类型，结果保持该类型。
- raw Python ``int`` / ``float`` 在算子边界自动 coerce 为 ``IntValue`` /
  ``FloatValue``（host adapter 行为）。
- ``int`` 与 ``float`` 不再隐式 promote；混用触发 ``unsupported-operation`` effect。
- 浮点溢出（``inf`` / ``nan``）触发 ``numeric-overflow`` effect。
"""

from __future__ import annotations

import pytest

from qy.errors import EvaluationError
from qy.errors import QyEffectSignal
from qy.frontend.reader import Symbol
from qy.runtime import evaluate
from qy.runtime import evaluate_source
from qy.sem.core import FloatValue
from qy.sem.core import IntValue

S = Symbol


# ---------------------------------------------------------------------------
# 基本行为
# ---------------------------------------------------------------------------


class TestPlusBasic:
    def test_two_integers(self):
        assert evaluate_source("(+ 1 2)") == IntValue(3)

    def test_multiple_integers(self):
        assert evaluate_source("(+ 1 2 3 4 5)") == IntValue(15)

    def test_zero_args_raises(self):
        # New semantics: ``(+)`` has no first argument to type-dispatch on.
        with pytest.raises(EvaluationError):
            evaluate_source("(+)")

    def test_single_arg_returns_itself(self):
        assert evaluate_source("(+ 42)") == IntValue(42)

    def test_negative_integers(self):
        assert evaluate_source("(+ -1 -2 -3)") == IntValue(-6)

    def test_mixed_positive_negative(self):
        assert evaluate_source("(+ 10 -3 5 -2)") == IntValue(10)


# ---------------------------------------------------------------------------
# 浮点数
# ---------------------------------------------------------------------------


class TestPlusFloat:
    def test_two_floats(self):
        assert evaluate_source("(+ 1.5 2.5)") == FloatValue(4.0)

    def test_int_and_float_no_implicit_promotion(self):
        # ``(+ int float)`` is unsupported under strict same-type semantics.
        with pytest.raises(QyEffectSignal) as exc_info:
            evaluate_source("(+ 1 2.5)")
        assert exc_info.value.effect == "unsupported-operation"

    def test_float_result_type(self):
        result = evaluate_source("(+ 1.0 2.0)")
        assert isinstance(result, FloatValue)

    def test_int_only_result_type(self):
        result = evaluate_source("(+ 1 2 3)")
        assert isinstance(result, IntValue)


# ---------------------------------------------------------------------------
# 嵌套表达式
# ---------------------------------------------------------------------------


class TestPlusNested:
    def test_nested_plus(self):
        assert evaluate_source("(+ 1 (+ 2 3))") == IntValue(6)

    def test_deeply_nested(self):
        assert evaluate_source("(+ (+ (+ 1 2) 3) 4)") == IntValue(10)

    def test_plus_in_other_arithmetic(self):
        assert evaluate_source("(* 2 (+ 3 4))") == IntValue(14)


# ---------------------------------------------------------------------------
# 非数字类型
# ---------------------------------------------------------------------------


class TestPlusTypeError:
    def test_string_arg_triggers_unsupported_operation(self):
        # Static analysis flags strings before runtime; runtime + would
        # otherwise raise an unsupported-operation effect for them.
        with pytest.raises(EvaluationError):
            evaluate_source('(+ 1 "hello")')

    def test_nil_arg_triggers_unsupported_operation(self):
        with pytest.raises(EvaluationError):
            evaluate_source("(+ 1 nil)")

    def test_bool_arg_rejected(self):
        # ``true`` is QY_T (a TValue), not a NumberValue.
        with pytest.raises(EvaluationError):
            evaluate_source("(+ true 1)")

    def test_all_non_number_raises(self):
        with pytest.raises(EvaluationError):
            evaluate((S("+"), "a", "b"))

    def test_error_message_mentions_type(self):
        with pytest.raises(EvaluationError, match="number"):
            evaluate((S("+"), "x"))


# ---------------------------------------------------------------------------
# 元数
# ---------------------------------------------------------------------------


class TestPlusArity:
    def test_zero_args_raises(self):
        with pytest.raises(EvaluationError):
            evaluate_source("(+)")

    def test_one_arg(self):
        assert evaluate_source("(+ 7)") == IntValue(7)

    def test_many_args(self):
        assert evaluate_source("(+ 1 2 3 4 5 6 7 8 9 10)") == IntValue(55)


# ---------------------------------------------------------------------------
# 从 Python API 调用（host-direct path）
# ---------------------------------------------------------------------------


class TestPlusFromPython:
    def test_evaluate_with_symbol_operator(self):
        assert evaluate((S("+"), 1, 2, 3)) == IntValue(6)

    def test_rejects_string_operator(self):
        with pytest.raises(EvaluationError):
            evaluate(("+", 1, 2))

    def test_evaluate_single_int(self):
        assert evaluate((S("+"), 42)) == IntValue(42)

    def test_evaluate_no_args_raises(self):
        with pytest.raises(EvaluationError):
            evaluate((S("+"),))

    def test_evaluate_floats(self):
        assert evaluate((S("+"), 1.5, 2.5)) == FloatValue(4.0)


# ---------------------------------------------------------------------------
# 边界值
# ---------------------------------------------------------------------------


class TestPlusBoundary:
    def test_zero(self):
        assert evaluate_source("(+ 0 0)") == IntValue(0)

    def test_large_integers(self):
        result = evaluate_source(f"(+ {10**18} {10**18})")
        assert result == IntValue(2 * 10**18)

    def test_very_small_float(self):
        result = evaluate_source("(+ 0.0000001 0.0000001)")
        assert isinstance(result, FloatValue)
        assert abs(result.value - 0.0000002) < 1e-15

    def test_infinity_triggers_overflow(self):
        # Float overflow (inf/nan) is mapped to numeric-overflow effect.
        with pytest.raises(QyEffectSignal) as exc_info:
            evaluate_source("(+ 1e308 1e308)")
        assert exc_info.value.effect == "numeric-overflow"

    def test_result_type_int_when_all_int(self):
        result = evaluate((S("+"), 1, 2))
        assert isinstance(result, IntValue)

    def test_result_type_float_when_all_float(self):
        result = evaluate((S("+"), 1.0, 2.0))
        assert isinstance(result, FloatValue)
