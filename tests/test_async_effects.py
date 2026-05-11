import pytest

from qy.errors import QyAggregateError
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
from qy.errors import QyPythonError
from qy.errors import format_qy_error
from qy.reader import Symbol
from qy.runtime import Qy

S = Symbol


async def test_py_native_python_exceptions_escape_as_unhandled_effect():
    qy = Qy()

    with pytest.raises(QyEffectSignal) as exc_info:
        await qy.evaluate_source_async(
            '''
            (py
              """
raise ValueError("bad")
""")
            '''
        )

    error = exc_info.value
    assert error.effect == "python-error"
    assert isinstance(error.cause, QyPythonError)
    assert isinstance(error.cause.cause, ValueError)
    formatted = format_qy_error(error, debug=True)
    assert "QY_UNHANDLED_EFFECT" in formatted
    assert "effect: python-error" in formatted
    assert "Python stack:" in formatted
    assert "ValueError: bad" in formatted


async def test_handle_can_catch_python_error_without_resume():
    qy = Qy()

    result = await qy.evaluate_source_async(
        '''
        (handle
          (py
            """
raise ValueError("bad")
""")
          ((python-error (err k) 'recovered)))
        '''
    )

    assert result == S("recovered")


async def test_resume_rejects_non_resumable_python_error():
    qy = Qy()

    with pytest.raises(QyEffectError, match="not resumable"):
        await qy.evaluate_source_async(
            '''
            (handle
              (py
                """
raise ValueError("bad")
""")
              ((python-error (err k) (resume k 'ignored))))
            '''
        )


async def test_perform_handle_resume_resumable_effect():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (let ()
          (defeffect ask)
          (handle
            (+ 1 (perform ask 41))
            ((ask (arg k) (resume k arg)))))
        """
    )

    assert result == 42


async def test_handle_without_resume_behaves_like_catch():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (let ()
          (defeffect fail)
          (handle
            (+ 1 (perform fail 41))
            ((fail (arg k) arg))))
        """
    )

    assert result == 41


async def test_resume_continues_body_after_perform():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (let ()
          (defeffect ask)
          (handle
            (let ()
              (perform ask 1)
              42)
            ((ask (arg k) (resume k arg)))))
        """
    )

    assert result == 42


async def test_assert_returns_truthy_condition():
    qy = Qy()

    result = await qy.evaluate_source_async('(assert true "ready")')

    assert result


async def test_assert_failure_raises_non_resumable_effect():
    qy = Qy()

    with pytest.raises(QyEffectSignal) as exc_info:
        await qy.evaluate_source_async('(assert false "missing title")')

    error = exc_info.value
    assert error.effect == "assert-failed"
    assert error.arg == S("missing title")
    assert not error.resumable
    assert error.span is not None


async def test_handle_can_catch_assert_failure_without_resume():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (handle
          (assert false "missing title")
          ((assert-failed (err k) 'debugged)))
        """
    )

    assert result == S("debugged")


async def test_resume_rejects_non_resumable_assert_failure():
    qy = Qy()

    with pytest.raises(QyEffectError, match="not resumable"):
        await qy.evaluate_source_async(
            """
            (handle
              (assert false "missing title")
              ((assert-failed (err k) (resume k true))))
            """
        )


async def test_resume_continues_into_assert_condition():
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (let ()
          (defeffect ask)
          (handle
            (assert (perform ask nil) "missing title")
            ((ask (arg k) (resume k true)))))
        """
    )

    assert result


async def test_parallel_raises_aggregate_error():
    qy = Qy()

    with pytest.raises(QyAggregateError) as exc_info:
        await qy.evaluate_source_async("(parallel missing absent)")

    error = exc_info.value
    assert error.code == "QY_AGGREGATE_ERROR"
    assert len(error.errors) == 2
    assert all(item.code == "QY_UNBOUND_SYMBOL" for item in error.errors)
