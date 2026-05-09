import sys
import unittest
from pathlib import Path

import lark

GRAMMER = """
?start: expressions
expressions: expression*

?expression: atom
    | list
    | quote_expression -> quote

?quote_expression: "'" expression
?list: "(" expression* ")"
?atom: STRING   -> string
    | SYMBOL    -> symbol
STRING: /"[^"]*"/
SYMBOL: /[a-zA-Z0-9_\-@:\.]+/
%import common.WS
%ignore WS
"""


class TestReader(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, "")

    def test_(self):
        from qy import symbol
        from qy._reader import tokenize

        tokens = tokenize(Path("examples/data.qy").read_text("utf-8"))
        print(list(tokens))
        parser = lark.Lark(GRAMMER)
        tree = parser.parse(Path("examples/data.qy").read_text("utf-8"))

        @lark.v_args(inline=True)
        class QyTransformer(lark.Transformer):
            def expressions(self, *tokens):
                return list(tokens)

            def quote(self, tokens):
                return ("quote", tokens)

            def string(self, token):
                return str(token[1:-1])

            def symbol(self, name):
                return symbol(name)

            def list(self, *items):
                return items

        transformer = QyTransformer()
        expr = transformer.transform(tree)
        print(expr)

    def test_reader(self):
        from qy import qy
        from qy.core import reader

        exp = reader("(+ 1 3)")[0]
        self.assertEqual(qy.eval(exp), 4)

    def tearDown(self):
        pass


if __name__ == "__main__":
    unittest.main()
