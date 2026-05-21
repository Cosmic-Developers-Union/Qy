# coding: utf-8

from __future__ import annotations

from lsprotocol import types

from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import read
from qy.runtime import Qy
from qy.tools.lsp.utils import shared_instance
from qy.tools.lsp.utils import symbol_name_at
from qy.tools.lsp.utils import symbol_start_at


def completion_items(
    source: str | None = None,
    line: int | None = None,
    character: int | None = None,
    *,
    qy: Qy | None = None,
) -> list[types.CompletionItem]:
    runtime = qy or shared_instance()
    items: list[types.CompletionItem] = []
    prefix = completion_prefix_at(source, line, character) if source is not None else ""
    items.extend(snippet_completion_items())
    for symbol, value in sorted(runtime.env.bindings().items(), key=lambda item: item[0].name):
        kind = getattr(value, "kind", None)
        doc = getattr(value, "doc", None)
        items.append(
            types.CompletionItem(
                label=symbol.name,
                kind=types.CompletionItemKind.Function
                if kind
                else types.CompletionItemKind.Variable,
                detail=f"{kind} operator" if kind else None,
                documentation=doc,
            )
        )
    if source is not None:
        items.extend(document_completion_items(source))
    if prefix:
        return [item for item in items if item.label.startswith(prefix)]
    return items


def snippet_completion_items() -> list[types.CompletionItem]:
    snippets = {
        "defun form": "(defun ${1:name} (${2:args})\n  ${0:body})",
        "let form": "(let ((${1:name} ${2:expr}))\n  ${0:body})",
        "lambda form": "(lambda (${1:arg})\n  ${0:body})",
        "cond form": "(cond\n  (${1:condition} ${0:result}))",
        "handle form": "(handle\n  ${1:expr}\n  ((${2:effect} (${3:arg} ${4:k}) ${0:body})))",
        "py form": '(py\n  """\n${0:return None}\n""")',
    }
    return [
        types.CompletionItem(
            label=label,
            kind=types.CompletionItemKind.Snippet,
            detail="Qy snippet",
            insert_text=insert_text,
            insert_text_format=types.InsertTextFormat.Snippet,
        )
        for label, insert_text in snippets.items()
    ]


def document_completion_items(source: str) -> list[types.CompletionItem]:
    try:
        forms = read(source)
    except ReaderSyntaxError:
        return []
    names = sorted({name.name for form in forms if (name := defined_name(form)) is not None})
    return [
        types.CompletionItem(
            label=name,
            kind=types.CompletionItemKind.Function,
            detail="document symbol",
        )
        for name in names
    ]


def completion_prefix_at(
    source: str | None,
    line: int | None,
    character: int | None,
) -> str:
    if source is None or line is None or character is None:
        return ""
    name = symbol_name_at(source, line, character)
    if name is None:
        return ""
    return name[: max(character - symbol_start_at(source, line, character), 0)]


def defined_name(form: Form) -> Symbol | None:
    from qy.core.syntax import Chain

    if not isinstance(form, Chain) or len(form) < 2 or not isinstance(form.head, Symbol):
        return None
    if form.head.name not in {"defun", "macro", "module", "defeffect"}:
        return None
    second = form.tail.head if isinstance(form.tail, Chain) else None
    return second if isinstance(second, Symbol) else None
