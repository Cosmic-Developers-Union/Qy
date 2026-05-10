import unittest

try:
    from lsprotocol import types

    from qy.lsp import QyLanguageServer
    from qy.lsp import completion_items
    from qy.lsp import create_server
    from qy.lsp import diagnostics_for_source
    from qy.lsp import hover_for_source
except ModuleNotFoundError as e:
    if e.name in {"lsprotocol", "pygls"}:
        raise unittest.SkipTest("pygls is an optional lsp dependency") from e
    raise


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

    def test_completion_items_include_builtins(self):
        labels = {item.label for item in completion_items()}

        self.assertIn("let", labels)
        self.assertIn("defun", labels)

    def test_hover_for_builtin_operator(self):
        hover = hover_for_source("(let ((x 1)) x)", 0, 1)

        self.assertIsNotNone(hover)
        assert hover is not None
        self.assertIsInstance(hover.contents, types.MarkupContent)


if __name__ == "__main__":
    unittest.main()
