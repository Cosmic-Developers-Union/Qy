# coding: utf-8
"""meta-interp: Qy 自举解释器的行为回归测试。.

对 ``meta-interp/cases/*.qy`` 中的每个样例，分别用：
- 参考路径：``qy run CASE``（host register VM 直接执行）
- 自举路径：``qy run meta-interp/main.qy -- CASE``（Qy 写的解释器执行）

并要求两者输出逐字节一致。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from qy.cli import create_app

ROOT = Path(__file__).resolve().parents[1]
META_INTERP = ROOT / "meta-interp" / "main.qy"
CASES = tuple(sorted((ROOT / "meta-interp" / "cases").glob("*.qy")))

# tests/qy 行为用例全集（批量跑，一次解释器进程）。
# 覆盖 quote/apply、作用域、递归、宏、模块、代数效应、parallel/all/race、
# 字符串、数字与 reify 等；每个用例都与 host register VM 输出逐字节对拍。
SUPPORTED_QY_TESTS = (
    "01_quote_apply",
    "02_scope_shadow",
    "03_effect_resume",
    "04_module_import",
    "05_define_once",
    "06_let_shadow",
    "07_nested_let",
    "08_defun_recursion",
    "09_pipeline",
    "10_string",
    "11_quote_chain",
    "12_cons_chain",
    "13_macro_basic",
    "14_parallel",
    "15_lambda",
    "16_cond",
    "17_nested_handle",
    "18_apply",
    "19_quasiquote_splice",
    "20_tail_recursion",
    "21_closure",
    "22_higher_order",
    "23_fold_from",
    "24_capture",
    "25_string_literal",
    "26_export_view",
    "27_all_barrier",
    "28_race_first",
    "29_nested_effects",
    "30_defeffect_basic",
    "31_macro_hygiene",
    "32_runtime_string",
    "33_pipeline_serial",
    "34_effect_state",
    "34_effect_with_define",
    "35_module_multi_export",
    "36_macro_module_import",
    "37_macro_gensym",
    "38_eq_identity",
    "38_module_function",
    "39_nil_only_cond",
    "40_eq_value_identity",
    "41_reify_basic",
    "42_number_add",
    "43_number_sub",
    "44_number_neg",
    "45_number_mul",
    "46_number_div",
    "47_number_mod",
    "48_number_lt",
    "49_number_gt",
    "50_number_le",
    "51_number_ge",
    "52_number_float_add",
    "53_number_bigint",
)

# examples/qy/validation 中运行代价可接受的样例。
# 03/09 是深度尾调用压力样例（分别约 4.5s / 29s），尾调用语义已由 tests/qy
# 的 20_tail_recursion 覆盖，默认测试不重复跑。
_EXCLUDED_VALIDATION = {
    "03_functions_tail_call.qy",
    "09_register_vm_tail_call.qy",
}
VALIDATION_EXAMPLES = tuple(
    path
    for path in sorted((ROOT / "examples" / "qy" / "validation").glob("*.qy"))
    if path.name not in _EXCLUDED_VALIDATION
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.mark.parametrize("case", CASES, ids=lambda path: path.stem)
def test_meta_interp_matches_reference(runner: CliRunner, case: Path) -> None:
    cli = create_app()
    reference = runner.invoke(cli, ["run", str(case)])
    assert reference.exit_code == 0, reference.output

    meta = runner.invoke(cli, ["run", str(META_INTERP), "--", str(case)])
    assert meta.exit_code == 0, meta.output
    assert meta.output == reference.output


@pytest.mark.parametrize("example", VALIDATION_EXAMPLES, ids=lambda path: path.stem)
def test_meta_interp_runs_validation_examples(runner: CliRunner, example: Path) -> None:
    """Examples/qy/validation 验收样例与 host register VM 输出逐字节一致。."""
    cli = create_app()
    reference = runner.invoke(cli, ["run", str(example)])
    assert reference.exit_code == 0, reference.output

    meta = runner.invoke(cli, ["run", str(META_INTERP), "--", str(example)])
    assert meta.exit_code == 0, meta.output
    assert meta.output == reference.output


def test_meta_interp_runs_supported_qytest_files(runner: CliRunner) -> None:
    """把受支持的 tests/qy 行为用例批量交给自举解释器，逐字节对齐参考输出。."""
    cli = create_app()
    paths = [ROOT / "tests" / "qy" / f"{name}.qy" for name in SUPPORTED_QY_TESTS]

    expected_parts: list[str] = []
    for path in paths:
        reference = runner.invoke(cli, ["run", str(path)])
        assert reference.exit_code == 0, (path, reference.output)
        expected_parts.append(reference.output)

    meta = runner.invoke(cli, ["run", str(META_INTERP), "--", *(str(p) for p in paths)])

    assert meta.exit_code == 0, meta.output
    assert meta.output == "".join(expected_parts)


def _stage2_source() -> str:
    """main.qy 去掉最后的 ``(interp-main)`` 驱动调用后，再追加一个内层程序。."""
    source = META_INTERP.read_text(encoding="utf-8")
    definitions = source.replace("\n(interp-main)\n", "\n")
    inner = "(+ 1 2)"
    return definitions + f'\n(interp-source "{inner}")\n'


@pytest.mark.skipif(
    not os.environ.get("QY_META_SELF"),
    reason="slow (self-interpretation); set QY_META_SELF=1 to run",
)
def test_meta_interp_interprets_its_own_source(runner: CliRunner, tmp_path: Path) -> None:
    """阶段 2：解释器源码被自身解释后，仍能解释 ``(+ 1 2)`` 得到 3。.

    输出包含内层 ``interp-source`` 打印的 ``3``；外层程序最后一个 form 的返回值
    是 ``nil``，按 ``qy run`` 规则同样被回显，因此末尾还有一行 ``nil``。
    """
    program = tmp_path / "self_stage2.qy"
    program.write_text(_stage2_source(), encoding="utf-8")

    cli = create_app()
    result = runner.invoke(cli, ["run", str(META_INTERP), "--", str(program)])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["3", "nil"]
