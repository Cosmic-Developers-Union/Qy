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


def test_quoted_string_is_str():
    assert read('abc "abc" "(not a list)" "hello world" ":size"') == [
        S("abc"),
        "abc",
        "(not a list)",
        "hello world",
        ":size",
    ]


def test_quoted_string_decodes_escapes():
    assert read(r'"hello\nworld" "quote: \"" "slash: \\"') == [
        "hello\nworld",
        'quote: "',
        "slash: \\",
    ]


def test_raw_quoted_string_preserves_escapes():
    assert read(r'r"\d+\s+" R"C:\path\to\file"') == [
        r"\d+\s+",
        r"C:\path\to\file",
    ]


def test_multiline_strings():
    assert read('"""hello\nworld""" r"""\\d+\\s+\nC:\\path"""') == [
        "hello\nworld",
        "\\d+\\s+\nC:\\path",
    ]


def test_tagged_literals_expand_to_tagged_quote_calls():
    assert read('t"hello {name}" sql"""select *\nfrom docs"""') == [
        (S("t"), (S("quote"), S("hello {name}"))),
        (S("sql"), (S("quote"), S("select *\nfrom docs"))),
    ]


def test_tagged_literals_decode_escapes():
    assert read(r't"hello\n{name}"') == [(S("t"), (S("quote"), S("hello\n{name}")))]
