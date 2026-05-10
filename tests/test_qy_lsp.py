import unittest

from lsprotocol import types

from qy.lsp import QyLanguageServer
from qy.lsp import create_server
from qy.lsp import diagnostics_for_source


class TestQyLsp(unittest.TestCase):
    def test_diagnostics_for_valid_source(self):
        self.assertEqual(diagnostics_for_source("(+ 1 2)"), [])

    def test_diagnostics_for_syntax_error(self):
        diagnostics = diagnostics_for_source("(+ 1")

        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].severity, types.DiagnosticSeverity.Error)
        self.assertEqual(diagnostics[0].source, "qy")

    def test_create_server(self):
        server = create_server()

        self.assertIsInstance(server, QyLanguageServer)


if __name__ == "__main__":
    unittest.main()
