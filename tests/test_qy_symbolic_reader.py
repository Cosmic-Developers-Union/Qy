import unittest

from qy.reader import DottedTuple
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import form_to_tuple
from qy.reader import get_span
from qy.reader import read
from qy.reader import read_one
from qy.reader import read_one_tuple
from qy.reader import read_tuple
from qy.reader import tuple_to_form
from qy.reader import write
from qy.reader import write_program
from qy.reader import write_tuple
from qy.reader import write_tuple_program

S = Symbol


class TestQySymbolicReader(unittest.TestCase):
    def test_bare_symbols(self):
        self.assertEqual(
            read("abc + 1 true nil :size ///path a.b a/b model:gpt-4.1"),
            [
                S("abc"),
                S("+"),
                S("1"),
                S("true"),
                S("nil"),
                S(":size"),
                S("///path"),
                S("a.b"),
                S("a/b"),
                S("model:gpt-4.1"),
            ],
        )

    def test_quoted_symbol_is_still_symbol(self):
        self.assertEqual(
            read('abc "abc" "(not a list)" "hello world" ":size"'),
            [
                S("abc"),
                S("abc"),
                S("(not a list)"),
                S("hello world"),
                S(":size"),
            ],
        )

    def test_quoted_symbol_decodes_escapes(self):
        self.assertEqual(
            read(r'"hello\nworld" "quote: \"" "slash: \\"'),
            [
                S("hello\nworld"),
                S('quote: "'),
                S("slash: \\"),
            ],
        )

    def test_raw_quoted_symbol_preserves_escapes(self):
        self.assertEqual(
            read(r'r"\d+\s+" R"C:\path\to\file"'),
            [
                S(r"\d+\s+"),
                S(r"C:\path\to\file"),
            ],
        )

    def test_multiline_symbols(self):
        self.assertEqual(
            read('"""hello\nworld""" r"""\\d+\\s+\nC:\\path"""'),
            [
                S("hello\nworld"),
                S("\\d+\\s+\nC:\\path"),
            ],
        )

    def test_tagged_literals_expand_to_tagged_quote_calls(self):
        self.assertEqual(
            read('t"hello {name}" sql"""select *\nfrom docs"""'),
            [
                (S("t"), (S("quote"), S("hello {name}"))),
                (S("sql"), (S("quote"), S("select *\nfrom docs"))),
            ],
        )

    def test_tagged_literals_decode_escapes(self):
        self.assertEqual(
            read(r't"hello\n{name}"'),
            [(S("t"), (S("quote"), S("hello\n{name}")))],
        )

    def test_list_and_quote_forms(self):
        self.assertEqual(
            read("'abc '\"abc\" '(+ 1 2)"),
            [
                (S("quote"), S("abc")),
                (S("quote"), S("abc")),
                (S("quote"), (S("+"), S("1"), S("2"))),
            ],
        )

    def test_dotted_pair_forms(self):
        form = read_one("(a . b)")

        self.assertIsInstance(form, DottedTuple)
        assert isinstance(form, DottedTuple)
        self.assertEqual(tuple(form), (S("a"),))
        self.assertEqual(form.tail, S("b"))
        self.assertEqual(write(form), "(a . b)")

    def test_invalid_dotted_pair_forms_are_rejected(self):
        with self.assertRaises(ReaderSyntaxError):
            read_one("(. b)")

    def test_let_binding_symbols_can_be_written_with_quotes(self):
        self.assertEqual(
            read_one('(let (("abc" 1)) abc "abc")'),
            (
                S("let"),
                ((S("abc"), S("1")),),
                S("abc"),
                S("abc"),
            ),
        )

    def test_comments_are_ignored_outside_quoted_symbols(self):
        self.assertEqual(
            read('(+ 1 ; ignored\n 2) ";not comment"'),
            [
                (S("+"), S("1"), S("2")),
                S(";not comment"),
            ],
        )

    def test_forms_keep_source_spans(self):
        form = read_one("(+ 1\n 2)")
        assert isinstance(form, tuple)
        form_span = get_span(form)
        last_item_span = get_span(form[2])

        assert form_span is not None
        assert last_item_span is not None
        self.assertEqual(form_span.line, 1)
        self.assertEqual(form_span.column, 1)
        self.assertEqual(last_item_span.line, 2)
        self.assertEqual(last_item_span.column, 2)

    def test_read_one_requires_exactly_one_form(self):
        with self.assertRaises(ReaderSyntaxError):
            read_one("")
        with self.assertRaises(ReaderSyntaxError):
            read_one("a b")

    def test_code_to_tuple_exchange_form(self):
        self.assertEqual(
            read_tuple('(load "my docs") (+ 1 2)'),
            [
                (S("load"), S("my docs")),
                (S("+"), S("1"), S("2")),
            ],
        )
        self.assertEqual(
            read_one_tuple('(let (("abc" 1)) abc "abc")'),
            (S("let"), ((S("abc"), S("1")),), S("abc"), S("abc")),
        )

    def test_tuple_exchange_form_to_qy_form(self):
        exchange_form = (S("embed"), (S("load"), S("docs")), S(":model"), S("text-embedding"))
        qy_form = (S("embed"), (S("load"), S("docs")), S(":model"), S("text-embedding"))

        self.assertEqual(tuple_to_form(exchange_form), qy_form)
        self.assertEqual(form_to_tuple(qy_form), exchange_form)

    def test_write_qy_form(self):
        self.assertEqual(write(S("abc")), "abc")
        self.assertEqual(write(S("hello world")), '"hello world"')
        self.assertEqual(write(S("(not a list)")), '"(not a list)"')
        self.assertEqual(write(S("hello\nworld")), r'"hello\nworld"')
        self.assertEqual(write((S("+"), S("1"), S("2"))), "(+ 1 2)")

    def test_write_tuple_exchange_form(self):
        source = write_tuple((S("embed"), (S("load"), S("my docs")), S(":size"), 800))
        self.assertEqual(source, '(embed (load "my docs") :size 800)')
        self.assertEqual(
            read_one_tuple(source),
            (S("embed"), (S("load"), S("my docs")), S(":size"), S("800")),
        )

    def test_write_programs(self):
        qy_forms = [S("abc"), (S("+"), S("1"), S("2"))]
        tuple_forms = [S("abc"), (S("+"), 1, 2)]

        self.assertEqual(write_program(qy_forms), "abc\n(+ 1 2)")
        self.assertEqual(write_tuple_program(tuple_forms), "abc\n(+ 1 2)")
        self.assertEqual(read_tuple(write_tuple_program(tuple_forms)), qy_forms)

    def test_python_string_tuple_atom_is_literal_not_symbol(self):
        with self.assertRaises(TypeError):
            tuple_to_form("abc")
        with self.assertRaises(TypeError):
            write_tuple("abc")


if __name__ == "__main__":
    unittest.main()
