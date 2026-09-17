# coding: utf-8
"""测量 MIR 优化序列的语义安全边界。.

用法::

    uv run python scripts/optimize_frontier.py            # 全语料
    uv run python scripts/optimize_frontier.py FILE ...   # 指定文件

做法：对每个 `.qy` **独立子进程**运行，比较「不优化」与各优化子集的结果，
结果做规范化（模块/函数/算子值折叠为类型名，避免 repr 里的内存地址造成假差异）。

为什么必须是子进程：优化 pass 与编译期/模块注册表存在进程级缓存，同一进程内
连续跑多个配置会出现顺序相关的假结果（P2-1 的早期测量就因此失真）。

子集按 **pass 索引** 选取：pass 的 ``name`` 可能重复（``optimize.dce`` 出现两次），
用名字过滤会把后面的 pass 一起选中。
"""

from __future__ import annotations

import glob
import subprocess
import sys
from collections import Counter

OPAQUE_TYPES = (
    "BytecodeFunctionValue",
    "StandardModule",
    "MacroDefinition",
    "EffectDefinition",
    "UserFunction",
    "ComponentOperator",
)
OPERATOR_TYPES = (
    "PureOperator",
    "ScopeOperator",
    "ControlOperator",
    "EffectOperator",
    "MetaOperator",
)

SUBSETS = {
    "S1 simplify": (0, 5),
    "S2 +cse/strength": (0, 7),
    "S3 +cfg/tailcall/licm/loop": (0, 11),
    "S4 +inline/scalar/intern": (0, 17),
    "S5 +reg_alloc": (0, 18),
}

_WORKER = r"""
import sys

from qy.async_utils import run_coro
from qy.build.pipeline import compile_source_to_bytecode
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.session.runtime_space import create_standard_runtime_space
from qy.vm.instance.machine import RegisterVirtualMachine
import qy.passes.optimize.apply as ap

OPAQUE = %(opaque)r
OPERATORS = %(operators)r
SUBSETS = %(subsets)r


def canon(value):
    name = type(value).__name__
    if name in OPAQUE:
        return (name,)
    if name in OPERATORS:
        return (name, getattr(value, "name", None))
    try:
        return (name, repr(value))
    except Exception:
        return (name,)


def run(source, indices, all_passes):
    ap.OPTIMIZE_PASSES = tuple(f for i, f in enumerate(all_passes) if i in indices)
    env = create_standard_runtime_space()
    result = compile_source_to_bytecode(
        source,
        PipelineSession(env=env),
        options=PipelineOptions(error_threshold=10 ** 6, optimize=bool(indices)),
    )
    if any(d.severity == "error" for d in result.diagnostics):
        return ("diag",)
    try:
        outcome = run_coro(RegisterVirtualMachine(result.artifact, env).evaluate_program())
    except Exception as e:  # noqa: BLE001 - 这里就是要把异常归类为结果
        return ("crash", type(e).__name__)
    return ("ok", tuple(canon(v) for v in (outcome or ())))


path = sys.argv[1]
source = open(path, encoding="utf-8").read()
all_passes = ap.OPTIMIZE_PASSES
base = run(source, frozenset(), all_passes)
bad = [name for name, (lo, hi) in SUBSETS.items() if run(source, frozenset(range(lo, hi)), all_passes) != base]
print(f"{path}\t{base[0]}\t{','.join(bad) or '-'}")
"""


def main(argv: list[str]) -> int:
    paths = argv or sorted(
        glob.glob("examples/qy/validation/*.qy")
        + glob.glob("examples/qy/design/*.qy")
        + glob.glob("tests/qy/*.qy")
        + glob.glob("meta-interp/cases/*.qy")
    )
    worker = _WORKER % {
        "opaque": OPAQUE_TYPES,
        "operators": OPERATOR_TYPES,
        "subsets": SUBSETS,
    }
    counts: Counter[str] = Counter()
    counts["files"] = len(paths)
    for path in paths:
        proc = subprocess.run(
            [sys.executable, "-c", worker, path],
            capture_output=True,
            text=True,
            check=False,
        )
        parts = proc.stdout.strip().split("\t")
        if len(parts) != 3:
            print(f"HARNESS-FAIL {path}: {proc.stderr.strip()[-200:]}", file=sys.stderr)
            continue
        _, base_kind, labels = parts
        counts[f"base_{base_kind}"] += 1
        for label in labels.split(","):
            if label and label != "-":
                counts[f"fail_{label}"] += 1

    print(
        f"files: {counts['files']}   base ok: {counts['base_ok']}   base diag: {counts['base_diag']}"
    )
    for name in SUBSETS:
        print(f"  {name:28s} mismatches={counts[f'fail_{name}']:2d}/{counts['files']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
