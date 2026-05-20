import pytest

from qy.evaluator import EvaluationError
from qy.evaluator import HostObjectRef
from qy.evaluator import standard_environment
from qy.reader import Symbol
from qy.runtime import AsyncQy as Qy
from qy.stdlib import load_module

S = Symbol


def _py_env():
    env = standard_environment()
    for sym, val in load_module("qy.py").exports.items():
        env.define(sym, val)
    return env


def _str_env():
    env = _py_env()
    for sym, val in load_module("qy.str").exports.items():
        env.define(sym, val)
    return env


async def test_py_runs_async_python_with_keyword_bindings():
    qy = Qy(env=_py_env())

    result = await qy.evaluate_source_async(
        '''
        (py
          """
return a + b
"""
          :a 20
          :b 22)
        '''
    )

    assert result == 42


async def test_py_converts_hyphenated_keywords_to_python_identifiers():
    qy = Qy(env=_py_env())

    result = await qy.evaluate_source_async(
        '''
        (py
          """
return user_name.upper()
"""
          :user-name "qy")
        '''
    )

    assert result == S("QY")


async def test_py_supports_await_and_awaits_returned_coroutines():
    qy = Qy(env=_py_env())

    result = await qy.evaluate_source_async(
        '''
        (py
          """
async def later():
    await asyncio.sleep(0)
    return value * 2
return later()
"""
          :value 21)
        '''
    )

    assert result == 42


async def test_py_wraps_qy_callables_as_async_python_functions():
    qy = Qy(env=_str_env())
    await qy.evaluate_source_async("(defun normalize-doc (doc) (str-upper doc))")

    result = await qy.evaluate_source_async(
        '''
        (py
          """
return await normalize(doc)
"""
          :doc "qy"
          :normalize normalize-doc)
        '''
    )

    assert result == S("QY")


async def test_py_converts_quoted_symbolic_literals_to_python_values():
    qy = Qy(env=_py_env())
    await qy.evaluate_source_async("(defun double (x) (* x 2))")

    result = await qy.evaluate_source_async(
        '''
        (py
          """
results = []
for v in values:
    results.append(await transform(v))
return results
"""
          :values '(1 2 3 4 5)
          :transform double)
        '''
    )

    assert result == [2, 4, 6, 8, 10]


async def test_py_converts_python_values_back_to_qy_values():
    qy = Qy(env=_py_env())

    result = await qy.evaluate_source_async(
        '''
        (py
          """
return ["qy", 1, None, {"name": "Qy"}]
""")
        '''
    )

    assert result == [S("qy"), 1, None, {S("name"): S("Qy")}]


async def test_py_preserves_core_data_types_across_bindings():
    qy = Qy(env=_py_env())

    result = await qy.evaluate_source_async(
        '''
        (py
          """
return [
    type(quoted).__name__,
    type(empty).__name__,
    list(quoted),
    isinstance(xs, list),
    isinstance(point, tuple),
    isinstance(doc, dict),
    isinstance(tags, set),
    doc["name"],
    sorted(tags),
]
"""
          :quoted '(1 2)
          :empty '()
          :xs (list 1 2 3)
          :point (tuple 10 20)
          :doc (dict "name" "Qy")
          :tags (set "core" "host"))
        '''
    )

    assert result == [
        S("QyChain"),
        S("QyNil"),
        [1, 2],
        True,
        True,
        True,
        True,
        S("Qy"),
        [S("core"), S("host")],
    ]


async def test_py_wraps_unknown_python_objects_as_host_refs():
    qy = Qy(env=_py_env())

    result = await qy.evaluate_source_async(
        '''
        (py
          """
return object()
""")
        '''
    )

    assert isinstance(result, HostObjectRef)


async def test_py_rejects_invalid_python_parameter_names():
    qy = Qy(env=_py_env())

    with pytest.raises(EvaluationError, match="valid Python identifier"):
        await qy.evaluate_source_async(
            '''
            (py
              """
return invalid_name
"""
              :invalid-name? 1)
            '''
        )
