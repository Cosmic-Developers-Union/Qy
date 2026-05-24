import pytest

from qy.errors import QyAggregateError
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
from qy.errors import QyPythonError
from qy.errors import format_qy_error
from qy.frontend.reader import Symbol
from qy.runtime import AsyncQy as Qy
from qy.std import load_module


def _py_env():
    qy = Qy()
    for sym, val in load_module("qy.py").exports.items():
        qy.env.define(sym, val)
    return qy


S = Symbol


async def test_py_native_python_exceptions_escape_as_unhandled_effect():
    qy = _py_env()

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
    qy = _py_env()

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
    qy = _py_env()

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
    assert error.arg == "missing title"
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
        await qy.evaluate_source_async("(parallel (eval (quote missing)) (eval (quote absent)))")

    error = exc_info.value
    assert error.code == "QY_AGGREGATE_ERROR"
    assert len(error.errors) == 2


async def test_resume_one_shot_continuation_raises_on_double_resume():
    """Multi-shot continuation: double resume produces sum of both branches."""
    qy = Qy()

    result = await qy.evaluate_source_async(
        """
        (defeffect ask)
        (handle
          (+ 1 (perform ask 41))
          ((ask (arg k)
            (+ (resume k arg) (resume k arg)))))
        """
    )

    assert result == 84


async def test_pipeline_returns_last_value():
    qy = Qy()
    result = await qy.evaluate_source_async("(pipeline 1 2 3)")
    assert result == 3


async def test_all_returns_aggregate_tuple():
    qy = Qy()
    result = await qy.evaluate_source_async("(all 10 20 30)")
    assert result == (10, 20, 30)


async def test_race_returns_one_value():
    qy = Qy()
    result = await qy.evaluate_source_async("(race 1 2 3)")
    assert result in (1, 2, 3)
