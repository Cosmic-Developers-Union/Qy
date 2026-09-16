# coding: utf-8
"""raw.validate pass：raw AST 只能是 symbol / chain / nil。."""

from __future__ import annotations

from typing import cast

from qy.core.syntax import Form
from qy.core.syntax import Symbol
from qy.core.syntax import list_to_chain
from qy.passes.raw.validate import validate_raw_forms


def test_valid_raw_forms_pass():
    forms = (
        Symbol("+"),
        list_to_chain([Symbol("+"), Symbol("1"), Symbol("2")]),
        list_to_chain([Symbol("a")], tail=Symbol("b")),
    )

    assert validate_raw_forms(forms) == ()


def test_host_value_in_raw_ast_is_an_error():
    forms = (list_to_chain([Symbol("list"), 1]),)

    diagnostics = validate_raw_forms(forms)

    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "error"
    assert "symbol/chain/nil" in diagnostics[0].message


def test_host_value_as_improper_tail_is_an_error():
    # 故意构造非法 datum：host str 出现在 improper tail
    forms = (list_to_chain([Symbol("a")], tail=cast(Form, "b")),)

    diagnostics = validate_raw_forms(forms)

    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "error"
