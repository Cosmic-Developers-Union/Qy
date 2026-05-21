# coding: utf-8


from qy.tools.lsp.utils import active_parameter
from qy.tools.lsp.utils import full_document_range
from qy.tools.lsp.utils import is_symbol_character
from qy.tools.lsp.utils import offset_at
from qy.tools.lsp.utils import operator_before_position
from qy.tools.lsp.utils import span_to_range
from qy.tools.lsp.utils import symbol_name_at
from qy.tools.lsp.utils import symbol_start_at


def test_is_symbol_character():
    assert is_symbol_character("a")
    assert is_symbol_character("1")
    assert is_symbol_character("-")
    assert is_symbol_character("+")
    assert not is_symbol_character(" ")
    assert not is_symbol_character("(")
    assert not is_symbol_character(")")
    assert not is_symbol_character('"')
    assert not is_symbol_character("'")
    assert not is_symbol_character(";")


def test_symbol_name_at():
    source = "(defun hello (x)\n  (+ x 1))"
    assert symbol_name_at(source, 0, 1) == "defun"
    assert symbol_name_at(source, 0, 7) == "hello"
    assert symbol_name_at(source, 0, 14) == "x"
    assert symbol_name_at(source, 1, 4) == "+"
    assert symbol_name_at(source, 1, 6) == "x"
    assert symbol_name_at(source, 0, 0) is None


def test_symbol_start_at():
    source = "(defun hello)"
    assert symbol_start_at(source, 0, 1) == 1
    assert symbol_start_at(source, 0, 5) == 1
    assert symbol_start_at(source, 0, 7) == 7
    assert symbol_start_at(source, 0, 12) == 7


def test_full_document_range():
    source = "line1\nline2\nline3"
    range_result = full_document_range(source)
    assert range_result.start.line == 0
    assert range_result.start.character == 0
    assert range_result.end.line == 3
    assert range_result.end.character == 5


def test_offset_at():
    source = "line1\nline2\nline3"
    assert offset_at(source, 0, 0) == 0
    assert offset_at(source, 0, 5) == 5
    assert offset_at(source, 1, 0) == 6
    assert offset_at(source, 1, 5) == 11
    assert offset_at(source, 2, 0) == 12


def test_operator_before_position():
    source = "(defun hello (x)\n  (+ x 1))"
    assert operator_before_position(source, 0, 7) == "defun"
    assert operator_before_position(source, 1, 6) == "+"
    assert operator_before_position(source, 0, 0) is None


def test_active_parameter():
    source = "(+ 1 2 3)"
    assert active_parameter(source, 0, 0) == 0
    assert active_parameter(source, 0, 3) == 0
    assert active_parameter(source, 0, 5) == 1
    assert active_parameter(source, 0, 7) == 2

    source = "(defun name (arg1 arg2) body)"
    assert active_parameter(source, 0, 7) == 0
    assert active_parameter(source, 0, 12) == 1
    assert active_parameter(source, 0, 24) == 1


def test_span_to_range():
    class MockSpan:
        def __init__(self, line, column, end_line, end_column):
            self.line = line
            self.column = column
            self.end_line = end_line
            self.end_column = end_column

    span = MockSpan(1, 1, 1, 5)
    range_result = span_to_range(span)
    assert range_result.start.line == 0
    assert range_result.start.character == 0
    assert range_result.end.line == 0
    assert range_result.end.character == 4
