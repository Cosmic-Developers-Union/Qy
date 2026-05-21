# coding: utf-8

from qy.tools.lsp.server import QyLanguageServer
from qy.tools.lsp.server import create_server


def test_create_server():
    server = create_server()
    assert isinstance(server, QyLanguageServer)
    assert server.qy is not None


def test_qy_language_server_init():
    server = QyLanguageServer()
    assert server.qy is not None
