# coding: utf-8
"""测试 qy.values 兼容层（向后兼容 shim）。."""

from __future__ import annotations

from qy.core.syntax import Chain
from qy.core.syntax import QyNil
from qy.core.syntax import nil
from qy.sem.core import T
from qy.sem.core import TValue


class TestShimSingletonIdentity:
    """验证 shim 的单例与规范位置一致。."""

    def test_nil_identity(self):
        from qy.values import QY_NIL

        assert QY_NIL is nil

    def test_nil_type_identity(self):
        from qy.values import QyNil

        assert QyNil is QyNil  # same class
        assert isinstance(nil, QyNil)

    def test_t_identity(self):
        from qy.values import QY_T

        assert QY_T is T

    def test_t_type_identity(self):
        from qy.values import QyT

        assert QyT is TValue

    def test_empty_chain_identity(self):
        from qy.values import QY_EMPTY_CHAIN

        assert QY_EMPTY_CHAIN is nil

    def test_empty_list_identity(self):
        from qy.values import QY_EMPTY_LIST

        assert QY_EMPTY_LIST is nil

    def test_qy_empty_chain_alias(self):
        from qy.values import QyEmptyChain

        assert QyEmptyChain is QyNil

    def test_qy_empty_list_alias(self):
        from qy.values import QyEmptyList

        assert QyEmptyList is QyNil


class TestShimTypeAliases:
    """验证 shim 的类型别名。."""

    def test_qy_chain_is_chain(self):
        from qy.values import QyChain

        assert QyChain is Chain

    def test_qy_cons_is_chain(self):
        from qy.values import QyCons

        assert QyCons is Chain

    def test_qy_cons_is_qy_chain(self):
        from qy.values import QyChain
        from qy.values import QyCons

        assert QyCons is QyChain


class TestShimBoolSemantics:
    """验证 shim 值的布尔语义。."""

    def test_nil_is_falsy(self):
        from qy.values import QY_NIL

        assert not bool(QY_NIL)

    def test_t_is_truthy(self):
        from qy.values import QY_T

        assert bool(QY_T)


class TestShimConstructors:
    """验证 shim 的构造函数。."""

    def test_list_to_qy_chain(self):
        from qy.values import list_to_qy_chain

        result = list_to_qy_chain([1, 2, 3])
        assert isinstance(result, Chain)
        assert result.head == 1
        assert result.tail.head == 2

    def test_list_to_qy_chain_empty(self):
        from qy.values import QY_NIL
        from qy.values import list_to_qy_chain

        result = list_to_qy_chain([])
        assert result is QY_NIL

    def test_list_to_qy_cons(self):
        from qy.values import list_to_qy_cons

        result = list_to_qy_cons([1, 2])
        assert isinstance(result, Chain)

    def test_iter_qy_chain(self):
        from qy.values import iter_qy_chain
        from qy.values import list_to_qy_cons

        chain = list_to_qy_cons([1, 2, 3])
        assert list(iter_qy_chain(chain)) == [1, 2, 3]

    def test_iter_qy_list(self):
        from qy.values import iter_qy_list
        from qy.values import list_to_qy_cons

        chain = list_to_qy_cons([42])
        assert list(iter_qy_list(chain)) == [42]

    def test_qy_chain_to_tuple(self):
        from qy.values import list_to_qy_cons
        from qy.values import qy_chain_to_tuple

        chain = list_to_qy_cons([1, 2, 3])
        assert qy_chain_to_tuple(chain) == (1, 2, 3)

    def test_qy_cons_to_tuple(self):
        from qy.values import list_to_qy_cons
        from qy.values import qy_cons_to_tuple

        chain = list_to_qy_cons([10, 20])
        assert qy_cons_to_tuple(chain) == (10, 20)


class TestShimPredicates:
    """验证 shim 的谓词。."""

    def test_chain_is_empty_true(self):
        from qy.values import QY_NIL
        from qy.values import qy_chain_is_empty

        assert qy_chain_is_empty(QY_NIL)

    def test_chain_is_empty_false(self):
        from qy.values import list_to_qy_cons
        from qy.values import qy_chain_is_empty

        chain = list_to_qy_cons([1])
        assert not qy_chain_is_empty(chain)

    def test_list_is_empty_true(self):
        from qy.values import QY_NIL
        from qy.values import qy_list_is_empty

        assert qy_list_is_empty(QY_NIL)

    def test_list_is_empty_false(self):
        from qy.values import list_to_qy_cons
        from qy.values import qy_list_is_empty

        chain = list_to_qy_cons([1])
        assert not qy_list_is_empty(chain)


class TestShimMap:
    """验证 shim 的 map 函数。."""

    def test_map_qy_cons(self):
        from qy.values import list_to_qy_cons
        from qy.values import map_qy_cons
        from qy.values import qy_cons_to_tuple

        chain = list_to_qy_cons([1, 2, 3])
        result = map_qy_cons(chain, lambda x: x * 2)
        assert qy_cons_to_tuple(result) == (2, 4, 6)

    def test_map_qy_chain(self):
        from qy.values import list_to_qy_chain
        from qy.values import map_qy_chain
        from qy.values import qy_chain_to_tuple

        chain = list_to_qy_chain([10, 20])
        result = map_qy_chain(chain, lambda x: x + 1)
        assert qy_chain_to_tuple(result) == (11, 21)

    def test_map_empty_chain(self):
        from qy.values import QY_NIL
        from qy.values import map_qy_chain

        result = map_qy_chain(QY_NIL, lambda x: x)
        assert result is QY_NIL

    def test_map_qy_chain_on_non_chain(self):
        from qy.values import map_qy_chain

        result = map_qy_chain(42, lambda x: x * 2)
        assert result == 84


class TestShimIterQyChainErrors:
    """验证 iter_qy_chain 的错误处理。."""

    def test_iter_improper_chain_raises(self):
        from qy.core.syntax import cons
        from qy.values import iter_qy_chain

        improper = cons(1, 2)
        gen = iter_qy_chain(improper)
        assert next(gen) == 1
        import pytest

        with pytest.raises(TypeError, match="expected a proper Qy chain"):
            next(gen)
