# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/std/*

from __future__ import annotations

import ast
from dataclasses import dataclass

from qy.reader import Symbol


@dataclass(frozen=True, slots=True)
class ImportSpec:
    name: Symbol
    alias: Symbol


def _decode_string_module(symbol: Symbol) -> Symbol:
    if symbol.name.startswith('"') or symbol.name.startswith('r"'):
        return Symbol(ast.literal_eval(symbol.name), symbol.span)
    return symbol


def parse_from_import(expression: tuple[object, ...]) -> tuple[Symbol, tuple[ImportSpec, ...]]:
    if len(expression) < 4:
        raise ValueError("from expects: (from module import name [as alias] ...)")

    head, module, import_keyword, *items = expression
    if head != Symbol("from"):
        raise ValueError(f"import form must start with 'from', got {head!r}")
    if not isinstance(module, Symbol):
        raise ValueError(f"module name must be a symbol or string path, got {module!r}")
    module = _decode_string_module(module)
    if import_keyword != Symbol("import"):
        raise ValueError("from expects the keyword 'import'")
    if not items:
        raise ValueError("from import expects at least one imported name")

    return module, _parse_import_items(tuple(items))


def _parse_import_items(items: tuple[object, ...]) -> tuple[ImportSpec, ...]:
    specs: list[ImportSpec] = []
    index = 0
    while index < len(items):
        item = items[index]
        if isinstance(item, tuple):
            specs.extend(_parse_import_items(item))
            index += 1
            continue
        if not isinstance(item, Symbol):
            raise ValueError(f"import name must be a symbol, got {item!r}")
        if item == Symbol("*"):
            raise ValueError("wildcard imports are not supported")
        if item == Symbol("as"):
            raise ValueError("'as' must follow an import name")

        alias = item
        if index + 1 < len(items) and items[index + 1] == Symbol("as"):
            if index + 2 >= len(items):
                raise ValueError("'as' must be followed by an alias")
            alias_item = items[index + 2]
            if not isinstance(alias_item, Symbol):
                raise ValueError(f"import alias must be a symbol, got {alias_item!r}")
            if alias_item in {Symbol("as"), Symbol("import")}:
                raise ValueError(f"invalid import alias {alias_item.name!r}")
            alias = alias_item
            index += 3
        else:
            index += 1

        specs.append(ImportSpec(item, alias))

    return tuple(specs)
