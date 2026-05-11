import unittest

try:
    from lsprotocol import types

    from qy.lsp import QyLanguageServer
    from qy.lsp import completion_items
    from qy.lsp import create_server
    from qy.lsp import diagnostics_for_source
    from qy.lsp import document_symbols_for_source
    from qy.lsp import hover_for_source
    from qy.lsp import signature_help_for_source
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
        self.assertIn("defun form", labels)

    def test_completion_items_include_document_symbols(self):
        labels = {item.label for item in completion_items("(defun local-add (a b) (+ a b))")}

        self.assertIn("local-add", labels)

    def test_hover_for_builtin_operator(self):
        hover = hover_for_source("(let ((x 1)) x)", 0, 1)

        self.assertIsNotNone(hover)
        assert hover is not None
        self.assertIsInstance(hover.contents, types.MarkupContent)

    def test_document_symbols_for_source(self):
        symbols = document_symbols_for_source("(defun local-add (a b) (+ a b))")

        self.assertEqual([symbol.name for symbol in symbols], ["local-add"])

    def test_signature_help_for_source(self):
        signature = signature_help_for_source("(defun square (x) (* x x))", 0, 7)

        self.assertIsNotNone(signature)
        assert signature is not None
        self.assertIn("defun", signature.signatures[0].label)


if __name__ == "__main__":
    unittest.main()
