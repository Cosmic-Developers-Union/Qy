# coding: utf-8

from __future__ import annotations

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from qy import __version__
from qy.runtime import Qy
from qy.tools.lsp.completion import completion_items
from qy.tools.lsp.diagnostics import diagnostics_for_source
from qy.tools.lsp.formatting import format_document
from qy.tools.lsp.hover import hover_for_source
from qy.tools.lsp.signature import signature_help_for_source
from qy.tools.lsp.symbols import document_symbols_for_source
from qy.tools.lsp.utils import shared_instance

SERVER_NAME = "qy-lsp"


class QyLanguageServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__(SERVER_NAME, __version__, types.TextDocumentSyncKind.Incremental)
        self.qy = shared_instance()


def create_server() -> QyLanguageServer:
    server = QyLanguageServer()

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(ls: QyLanguageServer, params: types.DidOpenTextDocumentParams) -> None:
        publish_diagnostics(ls, params.text_document.uri, params.text_document.text, ls.qy)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(ls: QyLanguageServer, params: types.DidChangeTextDocumentParams) -> None:
        document = ls.workspace.get_text_document(params.text_document.uri)
        publish_diagnostics(ls, document.uri, document.source, ls.qy)

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
        return format_document(document.source)

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


def publish_diagnostics(ls: QyLanguageServer, uri: str, source: str, qy: Qy) -> None:
    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=diagnostics_for_source(source, qy=qy),
        )
    )


def main() -> int:
    create_server().start_io()
    return 0
