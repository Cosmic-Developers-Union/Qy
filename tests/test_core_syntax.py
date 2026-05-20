# coding: utf-8
"""测试 qy.core.syntax 模块。.

测试 immutable Chain 类及相关操作。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from qy.core.syntax import Chain
from qy.core.syntax import car
from qy.core.syntax import cdr
from qy.core.syntax import chain_to_list
from qy.core.syntax import chain_to_tuple
from qy.core.syntax import cons
from qy.core.syntax import is_chain
from qy.core.syntax import is_nil
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil
from qy.core.syntax import tuple_to_chain
from qy.errors import SourceSpan


class TestBasicOperations:
    """测试基础 cons/car/cdr 操作。."""

    def test_cons_creates_chain(self):
        """测试 cons 创建 Chain。."""
        c = cons(1, nil)
        assert isinstance(c, Chain)
        assert c.head == 1
        assert c.tail is nil

    def test_car_returns_head(self):
        """测试 car 返回 head。."""
        c = cons(42, nil)
        assert car(c) == 42

    def test_cdr_returns_tail(self):
        """测试 cdr 返回 tail。."""
        c = cons(1, cons(2, nil))
        assert is_chain(cdr(c))
        assert car(cdr(c)) == 2

    def test_car_on_non_chain_raises(self):
        """测试 car 对非 Chain 抛出异常。."""
        with pytest.raises(TypeError, match="car expects a Chain"):
            car(42)

    def test_cdr_on_non_chain_raises(self):
        """测试 cdr 对非 Chain 抛出异常。."""
        with pytest.raises(TypeError, match="cdr expects a Chain"):
            cdr(42)


class TestPredicates:
    """测试谓词函数。."""

    def test_is_nil_on_nil(self):
        """测试 is_nil 识别 nil。."""
        assert is_nil(nil)

    def test_is_nil_on_chain(self):
        """测试 is_nil 对 Chain 返回 False。."""
        assert not is_nil(cons(1, nil))

    def test_is_nil_on_other_values(self):
        """测试 is_nil 对其他值返回 False。."""
        assert not is_nil(42)
        assert not is_nil("hello")
        assert not is_nil([])

    def test_is_chain_on_chain(self):
        """测试 is_chain 识别 Chain。."""
        assert is_chain(cons(1, nil))

    def test_is_chain_on_nil(self):
        """测试 is_chain 对 nil 返回 False。."""
        assert not is_chain(nil)

    def test_is_chain_on_other_values(self):
        """测试 is_chain 对其他值返回 False。."""
        assert not is_chain(42)
        assert not is_chain([1, 2, 3])


class TestListConversion:
    """测试 list/chain 转换。."""

    def test_list_to_chain_empty(self):
        """测试空列表转换。."""
        c = list_to_chain([])
        assert is_nil(c)

    def test_list_to_chain_single(self):
        """测试单元素列表转换。."""
        c = list_to_chain([42])
        assert is_chain(c)
        assert car(c) == 42
        assert is_nil(cdr(c))

    def test_list_to_chain_multiple(self):
        """测试多元素列表转换。."""
        c = list_to_chain([1, 2, 3])
        assert car(c) == 1
        assert car(cdr(c)) == 2
        assert car(cdr(cdr(c))) == 3
        assert is_nil(cdr(cdr(cdr(c))))

    def test_chain_to_list_empty(self):
        """测试空链转换。."""
        lst = chain_to_list(nil)
        assert lst == []

    def test_chain_to_list_single(self):
        """测试单元素链转换。."""
        c = cons(42, nil)
        lst = chain_to_list(c)
        assert lst == [42]

    def test_chain_to_list_multiple(self):
        """测试多元素链转换。."""
        c = list_to_chain([1, 2, 3])
        lst = chain_to_list(c)
        assert lst == [1, 2, 3]

    def test_list_to_chain_roundtrip(self):
        """测试往返转换。."""
        original = [1, "hello", 3.14, True]
        c = list_to_chain(original)
        result = chain_to_list(c)
        assert result == original


class TestTupleConversion:
    """测试 tuple/chain 转换（迁移期兼容）。."""

    def test_tuple_to_chain_empty(self):
        """测试空 tuple 转换。."""
        c = tuple_to_chain(())
        assert is_nil(c)

    def test_tuple_to_chain_single(self):
        """测试单元素 tuple 转换。."""
        c = tuple_to_chain((42,))
        assert car(c) == 42
        assert is_nil(cdr(c))

    def test_tuple_to_chain_multiple(self):
        """测试多元素 tuple 转换。."""
        c = tuple_to_chain((1, 2, 3))
        lst = chain_to_list(c)
        assert lst == [1, 2, 3]

    def test_chain_to_tuple_empty(self):
        """测试空链转 tuple。."""
        t = chain_to_tuple(nil)
        assert t == ()

    def test_chain_to_tuple_multiple(self):
        """测试多元素链转 tuple。."""
        c = list_to_chain([1, 2, 3])
        t = chain_to_tuple(c)
        assert t == (1, 2, 3)


class TestImproperList:
    """测试 improper list 支持。."""

    def test_cons_improper_list(self):
        """测试构造 improper list。."""
        c = cons(1, 2)  # (1 . 2)
        assert car(c) == 1
        assert cdr(c) == 2

    def test_list_to_chain_with_tail(self):
        """测试带 tail 的列表转换。."""
        c = list_to_chain([1, 2], tail=3)  # (1 2 . 3)
        assert car(c) == 1
        assert car(cdr(c)) == 2
        assert cdr(cdr(c)) == 3

    def test_chain_to_list_improper_raises(self):
        """测试 improper list 转 list 抛出异常。."""
        c = cons(1, 2)
        with pytest.raises(ValueError, match="Cannot convert improper list"):
            chain_to_list(c)

    def test_iterate_improper_list_raises(self):
        """测试迭代 improper list 抛出异常。."""
        c = cons(1, cons(2, 3))
        with pytest.raises(
            ValueError, match=r"Cannot iterate improper list|Cannot get length of improper list"
        ):
            list(c)

    def test_len_improper_list_raises(self):
        """测试获取 improper list 长度抛出异常。."""
        c = cons(1, 2)
        with pytest.raises(ValueError, match="Cannot get length of improper list"):
            len(c)


class TestIteration:
    """测试迭代器支持。."""

    def test_iterate_empty(self):
        """测试迭代空链。."""
        # nil 本身不是 Chain，不能直接迭代
        # 但 list_to_chain([]) 返回 nil
        assert list(iter([])) == []

    def test_iterate_single(self):
        """测试迭代单元素链。."""
        c = cons(42, nil)
        assert list(c) == [42]

    def test_iterate_multiple(self):
        """测试迭代多元素链。."""
        c = list_to_chain([1, 2, 3])
        assert list(cast("Chain", c)) == [1, 2, 3]

    def test_for_loop(self):
        """测试 for 循环。."""
        c = list_to_chain(["a", "b", "c"])
        result = []
        for item in cast("Chain", c):
            result.append(item)
        assert result == ["a", "b", "c"]


class TestLength:
    """测试长度计算。."""

    def test_len_single(self):
        """测试单元素链长度。."""
        c = cons(1, nil)
        assert len(c) == 1

    def test_len_multiple(self):
        """测试多元素链长度。."""
        c = list_to_chain([1, 2, 3, 4, 5])
        assert len(cast("Chain", c)) == 5


class TestSpanTracking:
    """测试 span 追踪。."""

    def test_cons_with_span(self):
        """测试带 span 的 cons。."""
        span = SourceSpan(source="test.qy", start_line=1, start_column=0)
        c = cons(1, nil, span=span)
        assert c.span is span

    def test_list_to_chain_with_span(self):
        """测试 list_to_chain 带 span。."""
        span = SourceSpan(source="test.qy", start_line=1, start_column=0)
        c = list_to_chain([1, 2, 3], span=span)
        # span 应该在最外层 Chain
        assert cast("Chain", c).span is span

    def test_span_not_in_equality(self):
        """测试 span 不参与相等性比较。."""
        span1 = SourceSpan(source="test1.qy", start_line=1, start_column=0)
        span2 = SourceSpan(source="test2.qy", start_line=2, start_column=5)

        c1 = cons(1, nil, span=span1)
        c2 = cons(1, nil, span=span2)
        c3 = cons(1, nil, span=None)

        # 相同的 head/tail，不同的 span，应该相等
        assert c1 == c2
        assert c1 == c3
        assert c2 == c3

    def test_span_not_in_repr(self):
        """测试 span 不出现在 repr 中。."""
        span = SourceSpan(source="test.qy", start_line=1, start_column=0)
        c = cons(1, nil, span=span)
        r = repr(c)
        # repr 不应该包含 span 信息
        assert "span" not in r.lower()


class TestImmutability:
    """测试不可变性。."""

    def test_chain_is_frozen(self):
        """测试 Chain 是 frozen 的。."""
        c = cons(1, nil)
        with pytest.raises(
            (AttributeError, TypeError, FrozenInstanceError)
        ):  # FrozenInstanceError or AttributeError
            setattr(c, "head", 2)  # noqa: B010

    def test_chain_has_slots(self):
        """测试 Chain 使用 slots。."""
        c = cons(1, nil)
        # slots 类不应该有 __dict__
        assert not hasattr(c, "__dict__")


class TestEdgeCases:
    """测试边界情况。."""

    def test_nested_chains(self):
        """测试嵌套 chain。."""
        inner = list_to_chain([1, 2])
        outer = list_to_chain([inner, 3])
        assert car(car(outer)) == 1

    def test_chain_with_none(self):
        """测试包含 None 的 chain。."""
        c = list_to_chain([1, None, 3])
        lst = chain_to_list(c)
        assert lst == [1, None, 3]

    def test_chain_with_mixed_types(self):
        """测试混合类型的 chain。."""
        c = list_to_chain([1, "hello", 3.14, True, None])
        lst = chain_to_list(c)
        assert lst == [1, "hello", 3.14, True, None]
