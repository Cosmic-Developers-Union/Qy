from qy.core.syntax import NONE as QY_NONE
from qy.core.syntax import Chain
from qy.core.syntax import Symbol
from qy.core.syntax import T as QY_T
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil as QY_EMPTY_LIST
from qy.core.syntax import nil as QY_NIL
from qy.runtime import evaluate_source

S = Symbol


def test_quote():
    assert evaluate_source("'abc") == S("abc")


def test_atom():
    assert evaluate_source("(atom 'abc)") is QY_T
    assert evaluate_source("(atom '(abc def))") is QY_NIL
    assert evaluate_source("(atom '(abc . def))") is QY_NIL
    assert evaluate_source("(atom '())") is QY_T


def test_cond():
    assert evaluate_source("(cond (0 'truthy))") == S("truthy")
    # false is now QY_NIL (nil-only truth), so first clause is skipped
    assert evaluate_source("(cond (false 1) (true (+ 1 2)))") == 3


def test_truthy():
    assert evaluate_source("(truthy 1)") is QY_T
    assert evaluate_source("(truthy none)") is QY_NIL
    assert evaluate_source("(truthy '())") is QY_NIL


def test_eq():
    # eq: value equality for atoms (symbol/number/string), identity for chains
    assert evaluate_source("(eq 'abc 'abc)") is QY_T  # same symbol name -> equal
    assert evaluate_source("(eq '(abc) '(abc))") is QY_NIL  # different QyCons
    assert evaluate_source("(eq '() '())") is QY_T  # both are QY_NIL singleton
    assert evaluate_source("(eq '() none)") is QY_NIL
    assert evaluate_source("(== '() none)") is QY_NIL
    assert evaluate_source("(eq nil '())") is QY_T  # both are QY_NIL
    assert evaluate_source("(eq none nil)") is QY_NIL
    assert evaluate_source("(eq T true)") is QY_T  # both resolve to QY_T
    assert evaluate_source("(== T true)") is QY_T  # both resolve to QY_T
    # string literals follow LANGUAGE.md string value equality
    assert evaluate_source('(eq "hello" "hello")') is QY_T
    assert evaluate_source('(eq "hello" "world")') is QY_NIL
    assert evaluate_source('(eq "1" 1)') is QY_NIL
    # char atoms also follow value equality
    assert evaluate_source("(eq #\\a #\\a)") is QY_T
    assert evaluate_source("(eq #\\a #\\b)") is QY_NIL
    assert evaluate_source("(eq #\\a 1.0)") is QY_NIL


def test_string_to_number():
    assert evaluate_source('(string->number "42")') == 42
    assert evaluate_source('(string->number "-3")') == -3
    assert evaluate_source('(string->number "2.5")') == 2.5
    assert evaluate_source('(string->number "abc")') is QY_NIL
    assert evaluate_source('(string->number "+")') is QY_NIL


def test_is():
    assert evaluate_source("(== '(abc) '(abc))") is QY_T
    assert evaluate_source("(is '(abc) '(abc))") is QY_NIL
    assert evaluate_source("(is '() '())") is QY_T


def test_literals():
    assert evaluate_source("nil") is QY_NIL
    assert evaluate_source("T") is QY_T
    assert evaluate_source("none") is QY_NONE


def test_type():
    assert evaluate_source("(type '(abc def))") == S("chain")
    assert evaluate_source("(type 'abc)") == S("symbol")
    assert evaluate_source("(type nil)") == S("nil")
    assert evaluate_source("(type T)") == S("T")
    assert evaluate_source("(type none)") == S("none")
    assert evaluate_source("(type #\\a)") == S("char")
    assert evaluate_source('(type "s")') == S("string")
    assert evaluate_source("(type 42)") == S("number")
    assert evaluate_source("(type car)") == S("operator")
    assert evaluate_source("(type (lambda (x) x))") == S("function")
    assert evaluate_source("(type (defeffect ask))") == S("effect")


def test_type_host_reference():
    from qy.sem.convert import to_qy_value
    from qy.session.runtime_space import create_standard_runtime_space

    env = create_standard_runtime_space()
    env.define(S("host"), to_qy_value(object()))
    assert evaluate_source("(type host)", env) == S("host")


def test_display_and_newline_operators(capsys):
    """`display` 不换行、`newline` 换行（与后端内建一致）。."""
    result = evaluate_source('(pipeline (display "a") (newline) (display "b") T)')

    assert capsys.readouterr().out == "a\nb"
    assert result is QY_T


def test_from_io_import_does_not_conflict_with_prelude():
    """顶层 `from qy.io import ...` 落在可写 head 层，不得与 qy.io 空间自身冲突。."""
    assert evaluate_source("(from qy.io import print) (print 1)") == 1
    assert evaluate_source("(from qy.io import display) (pipeline (display 1) T)") is QY_T


def test_host_reference_eq_is_identity_and_display_is_stable():
    """Host reference 是不透明引用类型：eq/is 按 identity；文本表示为 <host>。."""
    from qy.display import format_value
    from qy.sem.host import HostReference
    from qy.session.runtime_space import create_standard_runtime_space

    env = create_standard_runtime_space()
    reference = HostReference(object())
    env.define(S("host"), reference)
    env.define(S("host2"), HostReference(reference.value))
    assert evaluate_source("(eq host host)", env) is QY_T
    assert evaluate_source("(eq host host2)", env) is QY_NIL
    assert evaluate_source("(is host host)", env) is QY_T
    assert evaluate_source("(= 1 (get (dict host 1) host))", env) is QY_T
    assert format_value(reference) == "<host>"


def test_car_cdr_cons():
    assert evaluate_source("(car nil)") is QY_NIL
    assert evaluate_source("(cdr nil)") is QY_NIL
    assert evaluate_source("(car '(abc def))") == S("abc")
    assert evaluate_source("(cdr '(abc def ghi))") == list_to_chain([S("def"), S("ghi")])
    assert evaluate_source("(cons 'abc '(def ghi))") == list_to_chain(
        [S("abc"), S("def"), S("ghi")]
    )
    assert evaluate_source("'()") is QY_EMPTY_LIST
    assert evaluate_source("'(abc . def)") == Chain(S("abc"), S("def"))


def test_car_type_error_uses_qy_display():
    """`car`/`cdr` 的类型错误消息用 Qy display 渲染值，不泄漏宿主 repr。."""
    import pytest

    from qy.errors import QyTypeError

    with pytest.raises(QyTypeError, match="car expects a chain, got 1"):
        evaluate_source("(car 1)")
    with pytest.raises(QyTypeError, match="cdr expects a chain, got x"):
        evaluate_source('(cdr "x")')


def test_get_arity_and_len_message():
    """`get` 缺参报 QyArityError（不泄漏宿主 TypeError）；`len` 消息含 Qy display 值。."""
    import pytest

    from qy.errors import QyArityError
    from qy.errors import QyTypeError

    with pytest.raises(QyArityError, match="get expects two or three arguments, got 1"):
        evaluate_source("(get 0.0)")
    with pytest.raises(QyTypeError, match=r"len expects a collection, got 0\.0"):
        evaluate_source("(len 0.0)")


def test_reify_error_uses_qy_type_label():
    """`reify` 失败消息用 Qy 类型标签（与 `type` 一致），不泄漏宿主类名。."""
    import pytest

    from qy.errors import QyReifyError

    with pytest.raises(QyReifyError, match="cannot reify value of type set"):
        evaluate_source("(reify (set 1 2))")
    with pytest.raises(QyReifyError, match="cannot reify value of type function"):
        evaluate_source("(reify (lambda (x) x))")
    with pytest.raises(QyReifyError, match="cannot reify value of type operator"):
        evaluate_source("(reify +)")


def test_eval_compile_failure_is_clean_language_error():
    """`eval` 内层编译失败报语言级错误（未绑定符号为 QY_UNBOUND_SYMBOL），不漏 traceback。."""
    import pytest

    from qy.errors import QyResolveError
    from qy.errors import QyRuntimeError

    with pytest.raises(QyResolveError, match="unresolved symbol 'sym'"):
        evaluate_source("(eval (reify (quote sym)))")
    with pytest.raises(QyRuntimeError, match="eval: operator position is number"):
        evaluate_source("(eval (reify (quote (1 2))))")


def test_non_resumable_effect_cannot_be_resumed():
    """不可恢复 effect 的 continuation 调用报 QY_EFFECT_ERROR（与 TS/Go 一致）。."""
    import pytest

    from qy.errors import QyEffectError

    with pytest.raises(QyEffectError, match="not resumable"):
        evaluate_source("(handle (on divide-by-zero () k (resume k 42)) (mod 1 0))")


def test_char_case_rejects_multi_scalar_mapping():
    """char-upcase/char-downcase 的 full mapping 必须恰好一个 scalar，否则报 runtime error。."""
    import pytest

    from qy.display import format_value
    from qy.errors import QyRuntimeError

    with pytest.raises(QyRuntimeError, match="exactly one Unicode scalar"):
        evaluate_source("(from qy.char import char-upcase) (char-upcase #\\ß)")
    with pytest.raises(QyRuntimeError, match="exactly one Unicode scalar"):
        evaluate_source("(from qy.char import char-downcase) (char-downcase #\\İ)")
    assert (
        format_value(evaluate_source("(from qy.char import char-upcase) (char-upcase #\\a)")) == "A"
    )


def test_effect_payload_is_qy_dict():
    """Effect 载荷是 Qy `DictValue`（symbol 键 + Qy 值），不泄漏宿主 dict。."""
    from qy.display import format_value

    result = evaluate_source(
        "(from qy.int8 import int8 +) "
        "(handle (on numeric-overflow (v k) (get v 'operation)) "
        "(+ (int8 100) (int8 100)))"
    )

    assert format_value(result) == "+"

    type_result = evaluate_source(
        "(from qy.int8 import int8 +) "
        "(handle (on numeric-overflow (v k) (type v)) (+ (int8 100) (int8 100)))"
    )
    assert isinstance(type_result, Symbol) and type_result.name == "dict"


def test_lambda_arity_error_is_qy_arity_error():
    """参数数量不匹配报 QyArityError（QY_ARITY_ERROR），与 Go/TS 一致。."""
    import pytest

    from qy.errors import QyArityError

    with pytest.raises(QyArityError, match="f expects 1 arguments, got 0"):
        evaluate_source("(defun f (x) x) (f)")


def test_apply_uses_runtime_literals_for_quoted_args():
    assert evaluate_source("(apply + (quote (1 2 3)))") == 6


def test_quasiquote_unquote_splicing_works_without_internal_helpers():
    value = evaluate_source("(quasiquote (a (unquote-splicing (quote (b c))) d))")
    assert value == list_to_chain([S("a"), S("b"), S("c"), S("d")])
