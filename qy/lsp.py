# coding: utf-8

from __future__ import annotations

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from qy import __version__
from qy.analyzer import Diagnostic
from qy.analyzer import analyze_source
from qy.evaluator import standard_environment
from qy.formatter import format_source
from qy.reader import Symbol

SERVER_NAME = "qy-lsp"


class QyLanguageServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__(SERVER_NAME, __version__, types.TextDocumentSyncKind.Incremental)


def diagnostics_for_source(source: str) -> list[types.Diagnostic]:
    return [_diagnostic_to_lsp(diagnostic) for diagnostic in analyze_source(source).diagnostics]


def completion_items() -> list[types.CompletionItem]:
    items: list[types.CompletionItem] = []
    for symbol, value in sorted(
        standard_environment().bindings().items(), key=lambda item: item[0].name
    ):
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
    return items


def hover_for_source(source: str, line: int, character: int) -> types.Hover | None:
    name = _symbol_name_at(source, line, character)
    if name is None:
        return None
    try:
        value = standard_environment().resolve(Symbol(name))
    except Exception:
        return None

    kind = getattr(value, "kind", None)
    doc = getattr(value, "doc", "")
    if kind is None:
        return None
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
        _publish_diagnostics(ls, params.text_document.uri, params.text_document.text)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(ls: QyLanguageServer, params: types.DidChangeTextDocumentParams) -> None:
        document = ls.workspace.get_text_document(params.text_document.uri)
        _publish_diagnostics(ls, document.uri, document.source)

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
        del ls, params
        return types.CompletionList(is_incomplete=False, items=completion_items())

    @server.feature(types.TEXT_DOCUMENT_HOVER)
    def hover(ls: QyLanguageServer, params: types.HoverParams) -> types.Hover | None:
        document = ls.workspace.get_text_document(params.text_document.uri)
        return hover_for_source(
            document.source,
            params.position.line,
            params.position.character,
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

    return server


def main() -> int:
    create_server().start_io()
    return 0


def _publish_diagnostics(ls: QyLanguageServer, uri: str, source: str) -> None:
    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=diagnostics_for_source(source),
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


if __name__ == "__main__":
    raise SystemExit(main())
