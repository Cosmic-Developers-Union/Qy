# coding: utf-8
"""JSON 字节码交换格式的一致性测试。.

`qy export` 输出的 JSON 是所有宿主 VM（Python / Go / TypeScript）共享的字节码格式，
因此它必须满足两条契约：

1. **可表示**：程序里的每个常量都能编码（不得退化成 ``{"type":"unknown"}``）；
2. **可还原**：Python 侧装载后执行的结果与直接执行编译产物完全一致。

`Qy.run_bytecode_json` / `qy run --bytecode` 是这一格式的宿主入口。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from qy.backend.vm.bytecode import load_bytecode_json
from qy.backend.vm.bytecode import serialize_bytecode_json
from qy.build.pipeline import bytecode_artifact
from qy.build.pipeline import compile_source_to_kind
from qy.cli import create_app
from qy.core.syntax import NONE
from qy.core.syntax import T
from qy.core.syntax import nil
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.runtime import Qy
from qy.sem.core import IntValue
from qy.sem.core import StringValue
from qy.session.runtime_space import create_standard_runtime_space as standard_environment
from qy.vm.instance.machine import evaluate_bytecode

_QY_TEST_DIR = Path(__file__).resolve().parents[1] / "tests" / "qy"
_OPTIONS = PipelineOptions(error_threshold=10**6)


def _compile(source: str, env: object):
    return bytecode_artifact(
        compile_source_to_kind(source, PipelineSession(env=env), kind="bytecode", options=_OPTIONS)
    )


def test_round_trip_executes_every_qytest_program():
    """Tests/qy 的全部程序：编译 → 导出 → 装载 → **在全新环境**执行，结果必须一致。.

    注意必须用全新 env：交换格式必须自带运行所需的一切（hygiene 别名、模块宏导出），
    复用编译期 env 会让缺失的字段被编译期状态掩盖（这正是早期漏掉两个缺陷的原因）。
    """
    programs = sorted(_QY_TEST_DIR.glob("*.qy"))
    assert programs, "expected the qytest corpus"

    for path in programs:
        source = path.read_text(encoding="utf-8")
        compile_env = standard_environment()
        program = _compile(source, compile_env)
        text = serialize_bytecode_json(program, env=compile_env)

        assert '"type":"unknown"' not in text, f"{path.name}: unencodable constant in export"
        loaded = load_bytecode_json(text)

        direct = evaluate_bytecode(program, compile_env.child())
        # 装载结果在全新环境里执行：不共享编译期 env 的任何绑定
        restored = evaluate_bytecode(loaded, standard_environment())
        assert direct == restored, f"{path.name}: JSON round-trip changed the result"


def _synthetic_program(values: tuple[object, ...]):
    """构造一个把给定常量装进寄存器并返回的程序（用于编解码器单测）。。."""
    from qy.backend.vm.bytecode import BytecodeFunction
    from qy.backend.vm.bytecode import BytecodeProgram
    from qy.backend.vm.bytecode import Instruction
    from qy.core.syntax import Symbol

    instructions = (
        *(Instruction("LOAD_HOST", (index, value)) for index, value in enumerate(values)),
        Instruction("RETURN", (0,)),
    )
    function = BytecodeFunction(Symbol("<main>"), (), len(values), instructions)
    return BytecodeProgram((function,), 0)


def test_codec_covers_qy_value_kinds():
    """Qy 值必须按语义值编码，且往返后保持相等（单例保持同一对象）。。."""
    constants = (
        IntValue(7),
        StringValue("a"),
        nil,
        T,
        NONE,
        IntValue(-3),
    )
    text = serialize_bytecode_json(_synthetic_program(constants))
    data = json.loads(text)
    payloads = [
        operand
        for function in data["functions"]
        for instruction in function["instructions"]
        for operand in instruction["operands"]
    ]
    classes = {payload.get("class") for payload in payloads if "class" in payload}
    types = {payload.get("type") for payload in payloads}

    assert "unknown" not in types
    assert {"IntValue", "StringValue"} <= classes
    assert {"nil", "t", "none"} <= types

    loaded = load_bytecode_json(text)
    restored = [inst.operands[1] for inst in loaded.functions[0].instructions[:-1]]

    assert restored[0] == IntValue(7)
    assert restored[1] == StringValue("a")
    assert restored[2] is nil
    assert restored[3] is T
    assert restored[4] is NONE
    assert restored[5] == IntValue(-3)


def test_loader_rejects_unencodable_values():
    with pytest.raises(ValueError, match="unencodable value"):
        load_bytecode_json(
            json.dumps(
                {
                    "version": 1,
                    "main": 0,
                    "functions": [
                        {
                            "name": "<main>",
                            "params": [],
                            "register_count": 1,
                            "instructions": [
                                {
                                    "opcode": "LOAD_HOST",
                                    "operands": [
                                        {"type": "reg", "value": 0},
                                        {"type": "unknown", "value": "x"},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )
        )


def test_loader_rejects_unsupported_version():
    with pytest.raises(ValueError, match="unsupported bytecode JSON version"):
        load_bytecode_json(json.dumps({"version": 99, "main": 0, "functions": []}))


def test_qy_embedding_api_executes_exported_bytecode():
    env = standard_environment()
    program = _compile("(let ((x 40)) (+ x 2))", env)
    text = serialize_bytecode_json(program, env=env)

    qy = Qy(env=standard_environment())
    results = qy.run_bytecode_json(text)

    assert results == [IntValue(42)]


def test_cli_runs_exported_bytecode(tmp_path: Path):
    source_file = _QY_TEST_DIR / "01_quote_apply.qy"
    bytecode_file = tmp_path / "program.json"
    runner = CliRunner()
    cli = create_app()

    exported = runner.invoke(cli, ["export", str(source_file), "-o", str(bytecode_file)])
    assert exported.exit_code == 0, exported.output

    from_bytecode = runner.invoke(cli, ["run", "--bytecode", str(bytecode_file)])
    from_source = runner.invoke(cli, ["run", str(source_file)])

    assert from_bytecode.exit_code == 0, from_bytecode.output
    assert from_bytecode.output == from_source.output


def test_cli_runs_bytecode_from_stdin():
    env = standard_environment()
    program = _compile("(+ 20 22)", env)
    text = serialize_bytecode_json(program, env=env)
    runner = CliRunner()
    cli = create_app()

    result = runner.invoke(cli, ["run", "--bytecode", "-"], input=text)

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "42"


def test_value_singletons_survive_round_trip():
    """Nil / T / none 是单例，往返后必须仍是同一对象。。."""
    env = standard_environment()
    program = _compile("(list nil T none)", env)
    loaded = load_bytecode_json(serialize_bytecode_json(program, env=env))

    value = evaluate_bytecode(loaded, env.child())

    items = getattr(value, "items", ())
    assert items
    assert items[0] is nil
    assert items[1] is T
    assert items[2] is NONE


def test_hygiene_aliases_are_carried_by_the_exchange_format():
    """卫生宏产物必须能脱离编译期 env 执行（hygiene_bindings 必须被消费）。."""
    source = (_QY_TEST_DIR / "31_macro_hygiene.qy").read_text(encoding="utf-8")
    compile_env = standard_environment()
    program = _compile(source, compile_env)
    text = serialize_bytecode_json(program, env=compile_env)

    assert "hygiene_bindings" in text
    loaded = load_bytecode_json(text)
    assert loaded.hygiene_bindings, "loader must keep hygiene bindings"

    fresh = evaluate_bytecode(loaded, standard_environment())
    assert fresh == evaluate_bytecode(program, compile_env.child())


def test_module_macro_exports_are_carried_by_the_exchange_format():
    """模块的编译期宏导出名必须随字节码携带，否则运行期 `from` 会报缺导出。."""
    source = (_QY_TEST_DIR / "36_macro_module_import.qy").read_text(encoding="utf-8")
    compile_env = standard_environment()
    program = _compile(source, compile_env)
    text = serialize_bytecode_json(program, env=compile_env)

    assert "module_macro_exports" in text
    loaded = load_bytecode_json(text)
    assert dict(loaded.module_macro_exports).get("M") == ("my-add",)

    fresh = evaluate_bytecode(loaded, standard_environment())
    assert fresh == evaluate_bytecode(program, compile_env.child())


def test_cli_bytecode_path_matches_source_for_hygiene_and_module_macros(tmp_path: Path):
    """端到端：`qy export` 的产物用 `qy run --bytecode` 在新进程语义下执行。."""
    runner = CliRunner()
    cli = create_app()
    for name in ("19_quasiquote_splice.qy", "31_macro_hygiene.qy", "36_macro_module_import.qy"):
        source_file = _QY_TEST_DIR / name
        bytecode_file = tmp_path / f"{name}.json"
        exported = runner.invoke(cli, ["export", str(source_file), "-o", str(bytecode_file)])
        assert exported.exit_code == 0, exported.output

        from_bytecode = runner.invoke(cli, ["run", "--bytecode", str(bytecode_file)])
        from_source = runner.invoke(cli, ["run", str(source_file)])

        assert from_bytecode.exit_code == 0, (name, from_bytecode.output)
        assert from_bytecode.output == from_source.output, name
