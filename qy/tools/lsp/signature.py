# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.reader import Symbol
from qy.runtime import Qy
from qy.tools.lsp.utils import active_parameter
from qy.tools.lsp.utils import operator_before_position
from qy.tools.lsp.utils import shared_instance

SIGNATURES = {
    "defun": "(defun name (arg ...) body...)",
    "lambda": "(lambda (arg ...) body...)",
    "let": "(let ((name expr) ...) body...)",
    "cond": "(cond (condition result) ...)",
    "handle": "(handle expr ((effect (arg k) body...) ...))",
    "perform": "(perform effect arg)",
    "resume": "(resume k value)",
    "py": "(py source :name value ...)",
}


def signature_help_for_source(
    source: str,
    line: int,
    character: int,
    *,
    qy: Qy | None = None,
) -> types.SignatureHelp | None:
    runtime = qy or shared_instance()
    operator = operator_before_position(source, line, character)
    if operator is None:
        return None
    label = SIGNATURES.get(operator)
    if label is None:
        try:
            value = runtime.env.resolve(Symbol(operator))
        except Exception:
            return None
        doc = getattr(value, "doc", "")
        label = f"({operator} ...)"
    else:
        doc = ""
    return types.SignatureHelp(
        signatures=[
            types.SignatureInformation(
                label=label,
                documentation=doc or None,
            )
        ],
        active_signature=0,
        active_parameter=active_parameter(source, line, character),
    )
