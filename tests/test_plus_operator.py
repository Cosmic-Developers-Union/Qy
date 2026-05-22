"""全方位测试 + 算子的行为。."""

from __future__ import annotations

import math
from typing import cast

import pytest

from qy.evaluator import EvaluationError
from qy.evaluator import evaluate
from qy.evaluator import evaluate_source
from qy.frontend.reader import Symbol

S = Symbol


# ---------------------------------------------------------------------------
# 基本行为
# ---------------------------------------------------------------------------


class TestPlusBasic:
    """+ 的基本求值行为。."""

    def test_two_integers(self):
        """两个整数相加。."""
        assert evaluate_source("(+ 1 2)") == 3

    def test_multiple_integers(self):
        """多个整数相加。."""
        assert evaluate_source("(+ 1 2 3 4 5)") == 15

    def test_zero_args_returns_zero(self):
        """零个参数返回 0（Python sum([]) 的行为）。."""
        assert evaluate_source("(+)") == 0

    def test_single_arg_returns_itself(self):
        """单个参数原样返回。."""
        assert evaluate_source("(+ 42)") == 42

    def test_negative_integers(self):
        """负整数参与运算。."""
        assert evaluate_source("(+ -1 -2 -3)") == -6

    def test_mixed_positive_negative(self):
        """正负混合。."""
        assert evaluate_source("(+ 10 -3 5 -2)") == 10


# ---------------------------------------------------------------------------
# 浮点数
# ---------------------------------------------------------------------------


class TestPlusFloat:
    """浮点数参与 + 运算。."""

    def test_two_floats(self):
        assert evaluate_source("(+ 1.5 2.5)") == 4.0

    def test_int_and_float_promotes_to_float(self):
        assert evaluate_source("(+ 1 2.5)") == 3.5

    def test_float_result_type(self):
        """结果类型应为 float。."""
        result = evaluate_source("(+ 1.0 2.0)")
        assert isinstance(result, float)

    def test_int_only_result_type(self):
        """纯整数运算结果应为 int。."""
        result = evaluate_source("(+ 1 2 3)")
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# 嵌套表达式
# ---------------------------------------------------------------------------


class TestPlusNested:
    """嵌套 + 表达式。."""

    def test_nested_plus(self):
        assert evaluate_source("(+ 1 (+ 2 3))") == 6

    def test_deeply_nested(self):
        assert evaluate_source("(+ (+ (+ 1 2) 3) 4)") == 10

    def test_plus_in_other_arithmetic(self):
        assert evaluate_source("(* 2 (+ 3 4))") == 14


# ---------------------------------------------------------------------------
# 类型错误
# ---------------------------------------------------------------------------


class TestPlusTypeError:
    """非数字类型应抛出 QyTypeError。."""

    def test_string_arg_raises(self):
        with pytest.raises(EvaluationError):
            evaluate_source('(+ 1 "hello")')

    def test_nil_arg_raises(self):
        with pytest.raises(EvaluationError):
            evaluate_source("(+ 1 nil)")

    def test_bool_arg_raises(self):
        """布尔值虽然 Python 中是 int 子类，但 _ensure_number 显式拒绝。."""
        with pytest.raises(EvaluationError):
            evaluate_source("(+ true 1)")

    def test_list_arg_raises(self):
        with pytest.raises(EvaluationError):
            evaluate_source("(+ (chain 1 2) 3)")

    def test_all_non_number_raises(self):
        with pytest.raises(EvaluationError):
            evaluate((S("+"), "a", "b"))

    def test_error_message_mentions_type(self):
        """错误消息中应包含类型相关信息。."""
        with pytest.raises(EvaluationError, match="number"):
            evaluate((S("+"), "x"))


# ---------------------------------------------------------------------------
# 元数（arity）
# ---------------------------------------------------------------------------


class TestPlusArity:
    """+ 是 PureOperator，接受可变参数。."""

    def test_zero_args(self):
        assert evaluate_source("(+)") == 0

    def test_one_arg(self):
        assert evaluate_source("(+ 7)") == 7

    def test_many_args(self):
        assert evaluate_source("(+ 1 2 3 4 5 6 7 8 9 10)") == 55


# ---------------------------------------------------------------------------
# 从 Python API 调用
# ---------------------------------------------------------------------------


class TestPlusFromPython:
    """通过 Python API 调用 + 算子。."""

    def test_evaluate_with_symbol_operator(self):
        assert evaluate((S("+"), 1, 2, 3)) == 6

    def test_rejects_string_operator(self):
        with pytest.raises(EvaluationError):
            evaluate(("+", 1, 2))

    def test_evaluate_single_int(self):
        assert evaluate((S("+"), 42)) == 42

    def test_evaluate_no_args(self):
        assert evaluate((S("+"),)) == 0

    def test_evaluate_floats(self):
        assert evaluate((S("+"), 1.5, 2.5)) == 4.0


# ---------------------------------------------------------------------------
# 边界值
# ---------------------------------------------------------------------------


class TestPlusBoundary:
    """边界值与特殊情况。."""

    def test_zero(self):
        assert evaluate_source("(+ 0 0)") == 0

    def test_large_integers(self):
        result = evaluate_source(f"(+ {10**18} {10**18})")
        assert result == 2 * 10**18

    def test_very_small_float(self):
        result = cast(float, evaluate_source("(+ 0.0000001 0.0000001)"))
        assert abs(result - 0.0000002) < 1e-15

    def test_infinity(self):
        """Python float('inf') 参与 + 运算。."""
        result = cast(float, evaluate_source("(+ 1e308 1e308)"))
        assert math.isinf(result)

    def test_result_type_int_when_all_int(self):
        result = evaluate((S("+"), 1, 2))
        assert isinstance(result, int)
        assert not isinstance(result, bool)

    def test_result_type_float_when_any_float(self):
        result = evaluate((S("+"), 1, 2.0))
        assert isinstance(result, float)
