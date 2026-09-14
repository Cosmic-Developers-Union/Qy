# coding: utf-8
"""``qy.sem.bridge`` 宿主值 ↔ 语义值转换测试。."""

from __future__ import annotations

from qy.core.syntax import nil as QY_NIL
from qy.frontend.reader import Symbol
from qy.sem.bridge import from_qy_value
from qy.sem.bridge import to_qy_value
from qy.sem.core import NONE
from qy.sem.core import DictValue
from qy.sem.core import FloatValue
from qy.sem.core import IntValue
from qy.sem.core import ListValue
from qy.sem.core import SetValue
from qy.sem.core import StringValue
from qy.sem.core import T
from qy.sem.core import TupleValue
from qy.sem.host import HostReference


def test_to_qy_value_converts_host_primitives():
    assert to_qy_value(None) is NONE
    assert to_qy_value(True) is T
    assert to_qy_value(False) is QY_NIL
    assert to_qy_value(42) == IntValue(42)
    assert to_qy_value(2.5) == FloatValue(2.5)
    assert to_qy_value("qy") == StringValue("qy")


def test_to_qy_value_converts_host_containers():
    assert to_qy_value([1, "a"]) == ListValue((IntValue(1), StringValue("a")))
    assert to_qy_value((1, 2)) == TupleValue((IntValue(1), IntValue(2)))
    assert to_qy_value({"k": "v"}) == DictValue(((StringValue("k"), StringValue("v")),))
    assert to_qy_value({1}) == SetValue((IntValue(1),))


def test_unknown_host_objects_become_host_references():
    marker = object()
    converted = to_qy_value(marker)
    assert isinstance(converted, HostReference)
    assert converted.value is marker


def test_symbols_and_semantic_values_pass_through():
    symbol = Symbol("x")
    assert to_qy_value(symbol) is symbol
    value = StringValue("s")
    assert to_qy_value(value) is value
    reference = HostReference(object())
    assert to_qy_value(reference) is reference


def test_from_qy_value_unwraps_semantic_values():
    assert from_qy_value(StringValue("qy")) == "qy"
    assert from_qy_value(IntValue(3)) == 3
    assert from_qy_value(TupleValue((IntValue(1), StringValue("a")))) == (1, "a")
    assert from_qy_value(QY_NIL) is None
    marker = object()
    assert from_qy_value(HostReference(marker)) is marker


def test_bridge_round_trip_for_primitives():
    for host_value in (None, 3, 2.5, "text"):
        assert from_qy_value(to_qy_value(host_value)) == (
            None if host_value is None else host_value
        )
    # bool is host-level; T / nil are Qy objects and stay semantic values.
    assert to_qy_value(True) is T
    assert to_qy_value(False) is QY_NIL
