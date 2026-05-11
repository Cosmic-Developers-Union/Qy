from qy.reader import Symbol
from qy.reader import read

S = Symbol


def test_bare_symbols():
    assert read("abc + 1 true nil :size ///path a.b a/b model:gpt-4.1") == [
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
    ]


def test_quoted_symbol_is_still_symbol():
    assert read('abc "abc" "(not a list)" "hello world" ":size"') == [
        S("abc"),
        S("abc"),
        S("(not a list)"),
        S("hello world"),
        S(":size"),
    ]


def test_quoted_symbol_decodes_escapes():
    assert read(r'"hello\nworld" "quote: \"" "slash: \\"') == [
        S("hello\nworld"),
        S('quote: "'),
        S("slash: \\"),
    ]


def test_raw_quoted_symbol_preserves_escapes():
    assert read(r'r"\d+\s+" R"C:\path\to\file"') == [
        S(r"\d+\s+"),
        S(r"C:\path\to\file"),
    ]


def test_multiline_symbols():
    assert read('"""hello\nworld""" r"""\\d+\\s+\nC:\\path"""') == [
        S("hello\nworld"),
        S("\\d+\\s+\nC:\\path"),
    ]


def test_tagged_literals_expand_to_tagged_quote_calls():
    assert read('t"hello {name}" sql"""select *\nfrom docs"""') == [
        (S("t"), (S("quote"), S("hello {name}"))),
        (S("sql"), (S("quote"), S("select *\nfrom docs"))),
    ]


def test_tagged_literals_decode_escapes():
    assert read(r't"hello\n{name}"') == [(S("t"), (S("quote"), S("hello\n{name}")))]
