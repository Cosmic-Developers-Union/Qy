# coding: utf-8
"""内建算子表的一致性守卫。.

`qy/core/operator_builtins.py` 是内建算子 ABI 的唯一事实源；wasm / llvm 后端与
wasm 宿主 runtime（JS）都必须与它一致。这些检查把过去的"靠注释手工同步"变成
可执行不变量。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from qy.backend.llvm.abi import BUILTIN_NAMES as LLVM_BUILTIN_NAMES
from qy.backend.llvm.abi import BUILTIN_OPS
from qy.backend.wasm.abi import BUILTIN_NAMES as WASM_BUILTIN_NAMES
from qy.backend.wasm.abi import NUM_BUILTINS as WASM_NUM_BUILTINS
from qy.backend.wasm.abi import builtin_index as wasm_builtin_index
from qy.core.operator_builtins import BUILTIN_NAMES
from qy.core.operator_builtins import BUILTIN_OPERATORS
from qy.core.operator_builtins import NUM_BUILTINS
from qy.core.operator_builtins import builtin_index
from qy.core.syntax import Symbol
from qy.session.runtime_space import create_standard_runtime_space

_RUNTIME_JS = Path(__file__).resolve().parents[1] / "qy" / "resources" / "wasm" / "runtime.js"


def test_backend_tables_derive_from_canonical_source():
    assert tuple(WASM_BUILTIN_NAMES) == BUILTIN_NAMES
    assert tuple(LLVM_BUILTIN_NAMES) == BUILTIN_NAMES
    assert WASM_NUM_BUILTINS == NUM_BUILTINS == len(BUILTIN_NAMES)


def test_builtin_names_are_unique():
    names = list(BUILTIN_NAMES)

    assert len(names) == len(set(names))


def test_builtin_index_semantics():
    assert builtin_index("+") == 0
    assert builtin_index("not") == NUM_BUILTINS - 1
    assert wasm_builtin_index("+") == builtin_index("+")
    assert builtin_index("no-such-operator") == -1
    assert wasm_builtin_index("no-such-operator") == -1


def test_llvm_ops_match_canonical_declarations():
    assert set(BUILTIN_OPS) == set(BUILTIN_NAMES)
    for operator in BUILTIN_OPERATORS:
        assert BUILTIN_OPS[operator.name] == (operator.runtime_symbol, operator.arity)


def test_builtin_abi_arity_within_declared_operator_arity():
    """内建调用的固定元数必须是该算子声明元数的子集。."""
    env = create_standard_runtime_space()
    checked = 0
    for operator in BUILTIN_OPERATORS:
        try:
            value = env.resolve(Symbol(operator.name))
        except Exception:
            continue
        signature = getattr(value, "signature", None)
        arity = getattr(signature, "arity", None)
        if arity is None:
            continue
        maximum = arity.max if arity.max is not None else 1 << 30
        assert arity.min <= operator.arity <= maximum, (
            f"builtin {operator.name!r} ABI arity {operator.arity} "
            f"outside declared ({arity.min}, {arity.max})"
        )
        checked += 1
    assert checked, "expected at least one builtin with a declared arity"


def test_wasm_runtime_builtin_order_matches_canonical_source():
    """Wasm 宿主 runtime 的 builtins 数组顺序必须与事实源一致。."""
    source = _RUNTIME_JS.read_text(encoding="utf-8")
    match = re.search(r"const builtins = \[(.*?)\n  \];", source, re.S)
    assert match, "wasm runtime.js: const builtins array not found"

    entries = re.findall(r"/\*\s*(\d+)\s+(\S+?)\s*\*/", match.group(1))
    assert entries, "wasm runtime.js: builtin index comments not found"

    for index, name in entries:
        assert BUILTIN_NAMES[int(index)] == name, (
            f"wasm runtime.js builtin {index} is {name!r}, "
            f"canonical is {BUILTIN_NAMES[int(index)]!r}"
        )
    assert len(entries) == NUM_BUILTINS


def test_unknown_builtin_is_not_treated_as_builtin():
    with pytest.raises(ValueError):
        LLVM_BUILTIN_NAMES.index("no-such-operator")
