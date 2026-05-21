# coding: utf-8
# Migrated from qy/lsp.py

from __future__ import annotations

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from qy import __version__
from qy.analysis import Diagnostic
from qy.analysis import analyze_source
from qy.core.syntax import Chain
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import get_span
from qy.reader import read
from qy.runtime import Qy
from qy.tools.fmt import format_source

__all__ = [
    "QyLanguageServer",
    "completion_items",
    "create_server",
    "diagnostics_for_source",
    "document_symbols_for_source",
    "hover_for_source",
    "main",
    "signature_help_for_source",
]

SERVER_NAME = "qy-lsp"

_SHARED_INSTANCE: Qy | None = None


def _shared_instance() -> Qy:
    global _SHARED_INSTANCE
    if _SHARED_INSTANCE is None:
        _SHARED_INSTANCE = Qy()
    return _SHARED_INSTANCE


class QyLanguageServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__(SERVER_NAME, __version__, types.TextDocumentSyncKind.Incremental)
        self.qy = _shared_instance()


def diagnostics_for_source(source: str, *, qy: Qy | None = None) -> list[types.Diagnostic]:
    runtime = qy or _shared_instance()
    expansion = runtime.macroexpand_source(source)
    diagnostics = list(expansion.diagnostics)
    if not any(d.severity == "error" for d in diagnostics):
        analysis = analyze_source(source, runtime.env)
        diagnostics.extend(analysis.diagnostics)
    return [_diagnostic_to_lsp(diagnostic) for diagnostic in diagnostics]


_SIGNATURES = {
    "defun": "(defun name (arg ...) body...)",
    "lambda": "(lambda (arg ...) body...)",
    "let": "(let ((name expr) ...) body...)",
    "cond": "(cond (condition result) ...)",
    "handle": "(handle expr ((effect (arg k) body...) ...))",
    "perform": "(perform effect arg)",
    "resume": "(resume k value)",
    "py": "(py source :name value ...)",
}


def completion_items(
    source: str | None = None,
    line: int | None = None,
    character: int | None = None,
    *,
    qy: Qy | None = None,
) -> list[types.CompletionItem]:
    runtime = qy or _shared_instance()
    items: list[types.CompletionItem] = []
    prefix = _completion_prefix_at(source, line, character) if source is not None else ""
    items.extend(_snippet_completion_items())
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
        items.extend(_document_completion_items(source))
    if prefix:
        return [item for item in items if item.label.startswith(prefix)]
    return items


def hover_for_source(
    source: str,
    line: int,
    character: int,
    *,
    qy: Qy | None = None,
) -> types.Hover | None:
    runtime = qy or _shared_instance()
    name = _symbol_name_at(source, line, character)
    if name is None:
        return None
    try:
        value = runtime.env.resolve(Symbol(name))
    except Exception:
        return None

    kind = getattr(value, "kind", None)
    doc = getattr(value, "doc", "")
    if kind is None:
        doc = f"Qy value: `{type(value).__name__}`"
        kind = "value"
    return types.Hover(
        contents=types.MarkupContent(
            kind=types.MarkupKind.Markdown,
            value=f"**{name}** `{kind}`\n\n{doc}",
        )
    )


def create_server() -> QyLanguageServer:
    server = QyLanguageServer()

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(ls: QyLanguageServer, params: types.DidOpenTextDocumentParams) -> None:
        _publish_diagnostics(ls, params.text_document.uri, params.text_document.text, ls.qy)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(ls: QyLanguageServer, params: types.DidChangeTextDocumentParams) -> None:
        document = ls.workspace.get_text_document(params.text_document.uri)
        _publish_diagnostics(ls, document.uri, document.source, ls.qy)

    @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
    def did_close(ls: QyLanguageServer, params: types.DidCloseTextDocumentParams) -> None:
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(
                uri=params.text_document.uri,
                diagnostics=[],
            )
        )

    @server.feature(types.TEXT_DOCUMENT_COMPLETION)
    def completion(
        ls: QyLanguageServer,
        params: types.CompletionParams,
    ) -> types.CompletionList:
        document = ls.workspace.get_text_document(params.text_document.uri)
        return types.CompletionList(
            is_incomplete=False,
            items=completion_items(
                document.source,
                params.position.line,
                params.position.character,
                qy=ls.qy,
            ),
        )

    @server.feature(types.TEXT_DOCUMENT_HOVER)
    def hover(ls: QyLanguageServer, params: types.HoverParams) -> types.Hover | None:
        document = ls.workspace.get_text_document(params.text_document.uri)
        return hover_for_source(
            document.source,
            params.position.line,
            params.position.character,
            qy=ls.qy,
        )

    @server.feature(types.TEXT_DOCUMENT_FORMATTING)
    def formatting(
        ls: QyLanguageServer,
        params: types.DocumentFormattingParams,
    ) -> list[types.TextEdit]:
        document = ls.workspace.get_text_document(params.text_document.uri)
        return [
            types.TextEdit(
                range=_full_document_range(document.source),
                new_text=format_source(document.source),
            )
        ]

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def document_symbol(
        ls: QyLanguageServer,
        params: types.DocumentSymbolParams,
    ) -> list[types.DocumentSymbol]:
        document = ls.workspace.get_text_document(params.text_document.uri)
        return document_symbols_for_source(document.source)

    @server.feature(types.TEXT_DOCUMENT_SIGNATURE_HELP)
    def signature_help(
        ls: QyLanguageServer,
        params: types.SignatureHelpParams,
    ) -> types.SignatureHelp | None:
        document = ls.workspace.get_text_document(params.text_document.uri)
        return signature_help_for_source(
            document.source,
            params.position.line,
            params.position.character,
            qy=ls.qy,
        )

    return server


def document_symbols_for_source(source: str) -> list[types.DocumentSymbol]:
    try:
        forms = read(source)
    except ReaderSyntaxError:
        return []
    symbols: list[types.DocumentSymbol] = []
    for form in forms:
        symbol = _document_symbol_for_form(form)
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def signature_help_for_source(
    source: str,
    line: int,
    character: int,
    *,
    qy: Qy | None = None,
) -> types.SignatureHelp | None:
    runtime = qy or _shared_instance()
    operator = _operator_before_position(source, line, character)
    if operator is None:
        return None
    label = _SIGNATURES.get(operator)
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
        active_parameter=_active_parameter(source, line, character),
    )


def main() -> int:
    create_server().start_io()
    return 0


def _publish_diagnostics(ls: QyLanguageServer, uri: str, source: str, qy: Qy) -> None:
    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=diagnostics_for_source(source, qy=qy),
        )
    )


def _diagnostic_to_lsp(diagnostic: Diagnostic) -> types.Diagnostic:
    line = max((diagnostic.line or 1) - 1, 0)
    character = max((diagnostic.column or 1) - 1, 0)
    return types.Diagnostic(
        range=types.Range(
            start=types.Position(line=line, character=character),
            end=types.Position(line=line, character=character + 1),
        ),
        message=diagnostic.message,
        severity=_severity_to_lsp(diagnostic.severity),
        source="qy",
    )


def _severity_to_lsp(severity: str) -> types.DiagnosticSeverity:
    if severity == "warning":
        return types.DiagnosticSeverity.Warning
    if severity == "hint":
        return types.DiagnosticSeverity.Hint
    return types.DiagnosticSeverity.Error


def _full_document_range(source: str) -> types.Range:
    lines = source.splitlines()
    end_line = len(lines)
    end_character = 0 if not lines else len(lines[-1])
    return types.Range(
        start=types.Position(line=0, character=0),
        end=types.Position(line=end_line, character=end_character),
    )


def _symbol_name_at(source: str, line: int, character: int) -> str | None:
    lines = source.splitlines()
    if line >= len(lines):
        return None
    text = lines[line]
    if character > len(text):
        return None

    start = character
    while start > 0 and _is_symbol_character(text[start - 1]):
        start -= 1
    end = character
    while end < len(text) and _is_symbol_character(text[end]):
        end += 1
    if start == end:
        return None
    return text[start:end]


def _is_symbol_character(char: str) -> bool:
    return not char.isspace() and char not in """()"';"""


def _snippet_completion_items() -> list[types.CompletionItem]:
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


def _document_completion_items(source: str) -> list[types.CompletionItem]:
    try:
        forms = read(source)
    except ReaderSyntaxError:
        return []
    names = sorted({name.name for form in forms if (name := _defined_name(form)) is not None})
    return [
        types.CompletionItem(
            label=name,
            kind=types.CompletionItemKind.Function,
            detail="document symbol",
        )
        for name in names
    ]


def _document_symbol_for_form(form: Form) -> types.DocumentSymbol | None:
    name = _defined_name(form)
    if name is None:
        return None
    span = get_span(form) or name.span
    if span is None:
        return None
    kind = types.SymbolKind.Function
    if isinstance(form, Chain) and form.head == Symbol("module"):
        kind = types.SymbolKind.Module
    elif isinstance(form, Chain) and form.head == Symbol("defeffect"):
        kind = types.SymbolKind.Event
    return types.DocumentSymbol(
        name=name.name,
        kind=kind,
        range=_span_to_range(span),
        selection_range=_span_to_range(name.span or span),
    )


def _defined_name(form: Form) -> Symbol | None:
    if not isinstance(form, Chain) or len(form) < 2 or not isinstance(form.head, Symbol):
        return None
    if form.head.name not in {"defun", "macro", "module", "defeffect"}:
        return None
    second = form.tail.head if isinstance(form.tail, Chain) else None
    return second if isinstance(second, Symbol) else None


def _span_to_range(span) -> types.Range:
    return types.Range(
        start=types.Position(
            line=max((span.line or 1) - 1, 0), character=max((span.column or 1) - 1, 0)
        ),
        end=types.Position(
            line=max((span.end_line or span.line or 1) - 1, 0),
            character=max((span.end_column or span.column or 1) - 1, 0),
        ),
    )


def _completion_prefix_at(
    source: str | None,
    line: int | None,
    character: int | None,
) -> str:
    if source is None or line is None or character is None:
        return ""
    name = _symbol_name_at(source, line, character)
    if name is None:
        return ""
    return name[: max(character - _symbol_start_at(source, line, character), 0)]


def _symbol_start_at(source: str, line: int, character: int) -> int:
    lines = source.splitlines()
    if line >= len(lines):
        return character
    text = lines[line]
    start = min(character, len(text))
    while start > 0 and _is_symbol_character(text[start - 1]):
        start -= 1
    return start


def _operator_before_position(source: str, line: int, character: int) -> str | None:
    offset = _offset_at(source, line, character)
    prefix = source[:offset]
    open_index = prefix.rfind("(")
    if open_index == -1:
        return None
    index = open_index + 1
    while index < len(source) and source[index].isspace():
        index += 1
    start = index
    while index < len(source) and _is_symbol_character(source[index]):
        index += 1
    return source[start:index] or None


def _active_parameter(source: str, line: int, character: int) -> int:
    offset = _offset_at(source, line, character)
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


def _offset_at(source: str, line: int, character: int) -> int:
    lines = source.splitlines(keepends=True)
    if line >= len(lines):
        return len(source)
    return sum(len(item) for item in lines[:line]) + min(character, len(lines[line]))


if __name__ == "__main__":
    raise SystemExit(main())
