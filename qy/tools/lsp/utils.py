# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.runtime import Qy

_SHARED_INSTANCE: Qy | None = None


def shared_instance() -> Qy:
    global _SHARED_INSTANCE
    if _SHARED_INSTANCE is None:
        _SHARED_INSTANCE = Qy()
    return _SHARED_INSTANCE


def symbol_name_at(source: str, line: int, character: int) -> str | None:
    lines = source.splitlines()
    if line >= len(lines):
        return None
    text = lines[line]
    if character > len(text):
        return None

    start = character
    while start > 0 and is_symbol_character(text[start - 1]):
        start -= 1
    end = character
    while end < len(text) and is_symbol_character(text[end]):
        end += 1
    if start == end:
        return None
    return text[start:end]


def is_symbol_character(char: str) -> bool:
    return not char.isspace() and char not in """()"';"""


def full_document_range(source: str) -> types.Range:
    lines = source.splitlines()
    end_line = len(lines)
    end_character = 0 if not lines else len(lines[-1])
    return types.Range(
        start=types.Position(line=0, character=0),
        end=types.Position(line=end_line, character=end_character),
    )


def span_to_range(span) -> types.Range:
    return types.Range(
        start=types.Position(
            line=max((span.line or 1) - 1, 0), character=max((span.column or 1) - 1, 0)
        ),
        end=types.Position(
            line=max((span.end_line or span.line or 1) - 1, 0),
            character=max((span.end_column or span.column or 1) - 1, 0),
        ),
    )


def symbol_start_at(source: str, line: int, character: int) -> int:
    lines = source.splitlines()
    if line >= len(lines):
        return character
    text = lines[line]
    start = min(character, len(text))
    while start > 0 and is_symbol_character(text[start - 1]):
        start -= 1
    return start


def operator_before_position(source: str, line: int, character: int) -> str | None:
    offset = offset_at(source, line, character)
    prefix = source[:offset]
    open_index = prefix.rfind("(")
    if open_index == -1:
        return None
    index = open_index + 1
    while index < len(source) and source[index].isspace():
        index += 1
    start = index
    while index < len(source) and is_symbol_character(source[index]):
        index += 1
    return source[start:index] or None


def active_parameter(source: str, line: int, character: int) -> int:
    offset = offset_at(source, line, character)
    prefix = source[:offset]
    open_index = prefix.rfind("(")
    if open_index == -1:
        return 0
    depth = 0
    count = 0
    in_token = False
    for char in prefix[open_index + 1 :]:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        elif depth == 0 and char.isspace():
            if in_token:
                count += 1
                in_token = False
        elif depth == 0:
            in_token = True
    return max(count - 1, 0)


def offset_at(source: str, line: int, character: int) -> int:
    lines = source.splitlines(keepends=True)
    if line >= len(lines):
        return len(source)
    return sum(len(item) for item in lines[:line]) + min(character, len(lines[line]))
