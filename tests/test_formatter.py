from pathlib import Path

import pytest
from click.testing import CliRunner

from qy.cli import create_app
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import read
from qy.runtime import Qy
from qy.tools.fmt import dump_program
from qy.tools.fmt import format_source


def test_qy_fmt_method_basic():
    """Test Qy.fmt() method with basic formatting."""
    qy = Qy()
    assert qy.fmt("(+   1   2)") == "(+ 1 2)\n"


def test_qy_fmt_method_preserves_comments():
    """Test Qy.fmt() method preserves comments."""
    qy = Qy()
    result = qy.fmt("(+ 1 2) ; comment")
    assert "(+ 1 2)" in result
    assert "; comment" in result


def test_qy_fmt_method_syntax_error():
    """Test Qy.fmt() method raises ReaderSyntaxError on invalid syntax."""
    qy = Qy()
    try:
        qy.fmt("(+ 1 2")  # Missing closing paren
        raise AssertionError("Should have raised ReaderSyntaxError")
    except ReaderSyntaxError:
        pass  # Expected


def test_format_source_locks_simple_spacing():
    assert format_source("(+   1   2)") == "(+ 1 2)\n"


def test_format_source_expands_nested_forms():
    assert format_source("(defun square (x) (* x x))") == "(defun square (x) (* x x))\n"


def test_format_source_uses_quote_sugar():
    assert format_source("(quote abc)") == "'abc\n"


def test_format_source_quote_sugar_binding_is_idempotent():
    """(quote x) 作为 let 绑定名时仍须保持结构，且二次格式化稳定。."""
    source = "(let ((answer 'local) (quote 'shadowed)) answer)"
    once = format_source(source)
    assert format_source(once) == once


def test_format_source_normalizes_tagged_literals():
    assert format_source('t"hello"') == '(t \'"hello")\n'


def test_format_source_preserves_dotted_pairs():
    assert format_source("(a . b)") == "(a . b)\n"


def test_format_source_preserves_comments_and_blank_lines():
    assert (
        format_source("; head\n\n(+  1 2) ; sum\n; tail\n") == "; head\n\n(+ 1 2)  ; sum\n; tail\n"
    )


def test_format_source_preserves_comments_inside_forms():
    """Form 内部注释不得丢失（用 CST 原文渲染）。."""
    assert format_source("(+ 1 ; inner\n 2)") == "(+ 1 ; inner\n 2)\n"


def test_format_source_inline_comment_is_idempotent():
    source = "(defun f (x) ; doc\n (+ x 1))"
    once = format_source(source)
    assert "; doc" in once
    assert format_source(once) == once


def test_format_source_preserves_quoted_names():
    """引号前缀的符号名（如 'y）格式化后必须仍是同一符号。."""
    assert format_source("(define 'y 2)") == "(define 'y 2)\n"
    assert format_source("(let (('x 1)) 'x)") == "(let (('x 1)) 'x)\n"


def test_format_source_aligns_trailing_comments():
    assert format_source("(+ 1 2) ; a\n(* 10 20) ; b\n") == "(+ 1 2)    ; a\n(* 10 20)  ; b\n"


def test_format_source_ignores_semicolon_inside_strings():
    assert format_source('(print "a;b") ; ok') == '(print "a;b")  ; ok\n'


def test_dump_program_shows_ast():
    ast = dump_program(read("(+ 1 2)"))

    assert "Symbol('+')" in ast
    assert "Symbol('1')" in ast


def test_format_source_keeps_top_level_quote_with_its_operand():
    """顶层 `'form` / `` `form `` 不能被拆成前缀与操作数两个 form。."""
    assert format_source("'(a . 1)") == "'(a . 1)\n"
    assert format_source("'(a b)") == "'(a b)\n"
    assert format_source("`(a b)") == "`(a b)\n"
    assert format_source("'x") == "'x\n"
    assert format_source("'(a b) ; c") == "'(a b)  ; c\n"


def test_format_source_keeps_bare_quote_and_symbol_separate():
    """`' x` 是两个 form（操作数必须紧邻）；格式化不得把后一个 form 吞掉。."""
    assert format_source("' x").splitlines()[-1] == "x"
    assert format_source("'  (a b)").splitlines()[-1] == "(a b)"


# ─── corpus guards ───────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[1]
_FORMATTER_DIRS = (
    _ROOT / "tests" / "qy",
    _ROOT / "meta-interp" / "cases",
    _ROOT / "examples" / "qy" / "validation",
    _ROOT / "examples" / "qy" / "design",
)
_RUNNABLE_DIRS = _FORMATTER_DIRS[
    :2
]  # tests/qy + meta-interp/cases（validation 有深递归压力样例，跳过 CLI 重跑）


def _corpus(directories: tuple[Path, ...]) -> list[Path]:
    return sorted(path for directory in directories for path in directory.glob("*.qy"))


def _cli_output(path: Path) -> tuple[int, str]:
    result = CliRunner().invoke(create_app(), ["run", str(path)])
    return result.exit_code, result.output


@pytest.mark.parametrize("path", _corpus(_FORMATTER_DIRS), ids=lambda path: path.name)
def test_format_source_is_idempotent_over_corpus(path: Path):
    """Formatter 对全部语料幂等（历史上 design/00 曾非幂等）。."""
    source = path.read_text(encoding="utf-8")
    once = format_source(source)
    assert format_source(once) == once, f"{path.name}: format_source is not idempotent"


@pytest.mark.parametrize("path", _corpus(_RUNNABLE_DIRS), ids=lambda path: path.name)
def test_format_source_preserves_evaluation(path: Path, tmp_path: Path):
    """格式化前后 `qy run` 输出一致（含退出码）。."""
    source = path.read_text(encoding="utf-8")
    formatted_path = tmp_path / path.name
    formatted_path.write_text(format_source(source), encoding="utf-8")
    assert _cli_output(formatted_path) == _cli_output(path), path.name
