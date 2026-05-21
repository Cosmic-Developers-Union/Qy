# coding: utf-8

from lsprotocol import types

from qy.tools.lsp.symbols import document_symbols_for_source


def test_document_symbols_for_source():
    source = "(defun hello () body)\n(defun world () body)"
    symbols = document_symbols_for_source(source)
    assert len(symbols) == 2
    assert all(isinstance(s, types.DocumentSymbol) for s in symbols)
    assert symbols[0].name == "hello"
    assert symbols[1].name == "world"


def test_document_symbols_for_source_empty():
    source = ""
    symbols = document_symbols_for_source(source)
    assert len(symbols) == 0


def test_document_symbols_for_source_invalid():
    source = "(defun)"
    symbols = document_symbols_for_source(source)
    assert len(symbols) == 0


def test_document_symbols_module():
    source = "(module test-module)"
    symbols = document_symbols_for_source(source)
    assert len(symbols) == 1
    assert symbols[0].kind == types.SymbolKind.Module
