from qy.core.syntax import list_to_chain
from qy.reader import Symbol
from qy.reader import read

S = Symbol


def L(*items, span=None):
    """测试辅助：构造 Chain."""
    return list_to_chain(list(items), span=span)


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


def test_quoted_string_is_string_symbol():
    assert read('abc "abc" "(not a list)" "hello world" ":size"') == [
        S("abc"),
        S('"abc"'),
        S('"(not a list)"'),
        S('"hello world"'),
        S('":size"'),
    ]


def test_quoted_string_preserves_raw_escapes():
    assert read(r'"hello\nworld" "quote: \"" "slash: \\"') == [
        S(r'"hello\nworld"'),
        S(r'"quote: \""'),
        S(r'"slash: \\"'),
    ]


def test_raw_quoted_string_keeps_raw_prefix():
    assert read(r'r"\d+\s+" R"C:\path\to\file"') == [
        S(r'r"\d+\s+"'),
        S(r'R"C:\path\to\file"'),
    ]


def test_multiline_strings():
    assert read('"""hello\nworld""" r"""\\d+\\s+\nC:\\path"""') == [
        S('"""hello\nworld"""'),
        S('r"""\\d+\\s+\nC:\\path"""'),
    ]


def test_tagged_literals_expand_to_tagged_quote_calls():
    assert read('t"hello {name}" sql"""select *\nfrom docs"""') == [
        L(S("t"), L(S("quote"), S('"hello {name}"'))),
        L(S("sql"), L(S("quote"), S('"""select *\nfrom docs"""'))),
    ]


def test_tagged_literals_keep_raw_escapes():
    assert read(r't"hello\n{name}"') == [L(S("t"), L(S("quote"), S(r'"hello\n{name}"')))]
