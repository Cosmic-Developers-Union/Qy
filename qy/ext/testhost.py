# coding: utf-8
"""``qy.ext.testhost``：测试 / CLI 基础设施扩展。.

语言侧通过 ``(from qy.testhost import ...)`` 引入。该扩展声明
``filesystem`` / ``cli`` / ``coverage`` capability，只应由测试与工具链装载，
不进入标准 profile。
"""

from __future__ import annotations

from pathlib import Path

from qy.core.operators import ScopeOperator
from qy.core.syntax import Symbol
from qy.core.syntax import T as QY_T
from qy.core.syntax import list_to_chain
from qy.core.syntax import nil as QY_NIL
from qy.ext.descriptor import ExtensionBinding
from qy.ext.descriptor import ExtensionCapability
from qy.ext.descriptor import ExtensionDescriptor
from qy.ext.registry import register_extension
from qy.import_.module import StandardModule
from qy.session.runtime_space import RuntimeSpace as Environment

_CLI_ARGS_CACHE_KEY = ("qy", "cli_args")
_COVERAGE_INSTANCE_KEY = ("qy", "coverage_instance")


def module() -> StandardModule:
    return StandardModule(
        "qy.testhost",
        {
            Symbol("list-dir"): ScopeOperator("list-dir", _list_dir, "列出目录项（chain）。"),
            Symbol("path-join"): ScopeOperator("path-join", _path_join, "拼接路径。"),
            Symbol("file?"): ScopeOperator("file?", _is_file, "判断路径是否为文件。"),
            Symbol("dir?"): ScopeOperator("dir?", _is_dir, "判断路径是否为目录。"),
            Symbol("qy-file?"): ScopeOperator("qy-file?", _is_qy_file, "判断路径是否为 .qy 文件。"),
            Symbol("run-file"): ScopeOperator("run-file", _run_file, "运行 Qy 文件并返回结果。"),
            Symbol("run-file-with-coverage"): ScopeOperator(
                "run-file-with-coverage", _run_file_with_coverage, "运行 Qy 文件并收集覆盖率。"
            ),
            Symbol("start-coverage"): ScopeOperator(
                "start-coverage", _start_coverage, "启动覆盖率收集。"
            ),
            Symbol("stop-coverage"): ScopeOperator(
                "stop-coverage", _stop_coverage, "停止覆盖率收集。"
            ),
            Symbol("report-coverage"): ScopeOperator(
                "report-coverage", _report_coverage, "生成覆盖率报告。"
            ),
        },
    )


def _list_dir(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        return list_to_chain(())
    path_value = args[0]
    path = Path(_as_text(path_value)).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.is_dir():
        return list_to_chain(())
    entries = tuple(
        Symbol(item.name) for item in sorted(path.iterdir(), key=lambda item: item.name)
    )
    return list_to_chain(entries)


def _path_join(args: tuple[object, ...], env: Environment) -> Symbol:
    del env
    if len(args) != 2:
        return Symbol("")
    base_path = Path(_as_text(args[0]))
    joined = base_path / _as_text(args[1])
    return Symbol(str(joined))


def _is_file(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        return QY_NIL
    path_value = args[0]
    path = Path(_as_text(path_value)).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return QY_T if path.is_file() else QY_NIL


def _is_dir(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        return QY_NIL
    path_value = args[0]
    path = Path(_as_text(path_value)).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return QY_T if path.is_dir() else QY_NIL


def _is_qy_file(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        return QY_NIL
    path = Path(_as_text(args[0])).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return QY_T if (path.is_file() and path.suffix == ".qy") else QY_NIL


async def _run_file(args: tuple[object, ...], env: Environment) -> object:
    if len(args) != 1:
        return QY_NIL
    path_value = args[0]
    path = Path(_as_text(path_value)).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    try:
        from qy import AsyncQy

        qy = AsyncQy()
        result = await qy.evaluate_file(path)
        return QY_T if result is not QY_NIL else QY_NIL
    except Exception:
        return QY_NIL


def _as_text(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    return str(value)


def _start_coverage(args: tuple[object, ...], env: Environment) -> object:
    """启动覆盖率收集."""
    del args
    try:
        import coverage

        cov = coverage.Coverage(source=["qy"], omit=["*/tests/*", "*/test_*.py"])
        cov.start()
        env.cache_define(_COVERAGE_INSTANCE_KEY, cov)
        return QY_T
    except ImportError:
        return QY_NIL


def _stop_coverage(args: tuple[object, ...], env: Environment) -> object:
    """停止覆盖率收集."""
    del args
    try:
        from typing import Any

        cov: Any = env.cache_lookup(_COVERAGE_INSTANCE_KEY)
        if cov is not None and hasattr(cov, "stop"):
            cov.stop()
            return QY_T
    except (KeyError, AttributeError):
        pass
    return QY_NIL


def _report_coverage(args: tuple[object, ...], env: Environment) -> object:
    """生成覆盖率报告."""
    del args
    try:
        from typing import Any

        cov: Any = env.cache_lookup(_COVERAGE_INSTANCE_KEY)
        if cov is not None and hasattr(cov, "save"):
            cov.save()
            print("\n" + "=" * 70)
            print("Coverage Report:")
            print("=" * 70)
            cov.report()
            cov.json_report(outfile="coverage.json")
            print("=" * 70)
            print("Coverage JSON written to coverage.json")
            return QY_T
    except (KeyError, AttributeError):
        pass
    return QY_NIL


async def _run_file_with_coverage(args: tuple[object, ...], env: Environment) -> object:
    """运行文件并收集覆盖率."""
    if len(args) != 1:
        return QY_NIL
    path_value = args[0]
    path = Path(_as_text(path_value)).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    try:
        from qy import AsyncQy

        qy = AsyncQy()
        result = await qy.evaluate_file(path)
        return QY_T if result is not QY_NIL else QY_NIL
    except Exception:
        return QY_NIL


DESCRIPTOR = ExtensionDescriptor(
    name="qy.ext.testhost",
    module_name="qy.testhost",
    version="0.1",
    description="测试 / CLI 基础设施扩展（目录、文件、CLI 参数、覆盖率）。",
    capabilities=(
        ExtensionCapability("filesystem", "读取目录与文件状态"),
        ExtensionCapability("coverage", "启动/停止覆盖率收集（可选）"),
    ),
    bindings=(
        ExtensionBinding("cli-args", kind="scope", doc="读取 CLI 传入的额外参数。"),
        ExtensionBinding("list-dir", kind="scope", doc="列出目录项。"),
        ExtensionBinding("path-join", kind="scope", doc="拼接路径。"),
        ExtensionBinding("file?", kind="scope", doc="判断路径是否为文件。"),
        ExtensionBinding("dir?", kind="scope", doc="判断路径是否为目录。"),
        ExtensionBinding("qy-file?", kind="scope", doc="判断路径是否为 .qy 文件。"),
        ExtensionBinding("lookup-export", kind="scope", doc="解析宿主模块导出。"),
        ExtensionBinding("display", kind="scope", doc="按 Qy display 规则格式化值。"),
        ExtensionBinding("raise-error", kind="scope", doc="以语言级错误终止求值。"),
        ExtensionBinding("gensym", kind="scope", doc="生成全新 symbol。"),
        ExtensionBinding("run-file", kind="scope", doc="运行 Qy 文件。"),
        ExtensionBinding("run-file-with-coverage", kind="scope", doc="运行文件并收集覆盖率。"),
        ExtensionBinding("start-coverage", kind="scope", doc="启动覆盖率收集。"),
        ExtensionBinding("stop-coverage", kind="scope", doc="停止覆盖率收集。"),
        ExtensionBinding("report-coverage", kind="scope", doc="生成覆盖率报告。"),
    ),
)

register_extension(DESCRIPTOR, module)
