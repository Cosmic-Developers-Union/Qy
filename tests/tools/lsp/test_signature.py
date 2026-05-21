# coding: utf-8

from qy.tools.lsp.signature import SIGNATURES
from qy.tools.lsp.signature import signature_help_for_source


def test_signature_help_for_source_builtin():
    source = "(defun hello (x) body)"
    help_result = signature_help_for_source(source, 0, 10)
    assert help_result is not None
    assert len(help_result.signatures) > 0
    assert "defun" in help_result.signatures[0].label


def test_signature_help_for_source_no_operator():
    source = "hello"
    help_result = signature_help_for_source(source, 0, 2)
    assert help_result is None


def test_signatures_constant():
    assert "defun" in SIGNATURES
    assert "lambda" in SIGNATURES
    assert "let" in SIGNATURES
    assert "cond" in SIGNATURES
