# coding: utf-8

from __future__ import annotations

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from qy import __version__
from qy.reader import ReaderSyntaxError
from qy.reader import read

SERVER_NAME = "qy-lsp"


class QyLanguageServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__(SERVER_NAME, __version__, types.TextDocumentSyncKind.Incremental)


def diagnostics_for_source(source: str) -> list[types.Diagnostic]:
    try:
        read(source)
    except ReaderSyntaxError as e:
        return [_syntax_error_diagnostic(e)]
    return []


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


def _syntax_error_diagnostic(error: ReaderSyntaxError) -> types.Diagnostic:
    line = max((error.line or 1) - 1, 0)
    character = max((error.column or 1) - 1, 0)
    return types.Diagnostic(
        range=types.Range(
            start=types.Position(line=line, character=character),
            end=types.Position(line=line, character=character + 1),
        ),
        message=str(error),
        severity=types.DiagnosticSeverity.Error,
        source="qy",
    )


if __name__ == "__main__":
    raise SystemExit(main())
