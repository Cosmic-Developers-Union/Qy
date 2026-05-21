# coding: utf-8

from __future__ import annotations

from pathlib import Path

from qy.core.operators import ScopeOperator
from qy.core.syntax import list_to_chain
from qy.environment import Environment
from qy.reader import Symbol
from qy.std.module import StandardModule
from qy.values import QY_NIL
from qy.values import QY_T

_CLI_ARGS_CACHE_KEY = ("qy", "cli_args")
_COVERAGE_INSTANCE_KEY = ("qy", "coverage_instance")


def module() -> StandardModule:
    return StandardModule(
        "qy.testhost",
        {
            Symbol("cli-args"): ScopeOperator(
                "cli-args",
                _cli_args,
                "读取 CLI 传入的额外参数（chain of symbol）。",
            ),
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


def set_cli_args(env: Environment, args: tuple[str, ...]) -> None:
    env.cache_define(_CLI_ARGS_CACHE_KEY, tuple(args))


def _cli_args(args: tuple[object, ...], env: Environment) -> object:
    if args:
        return list_to_chain(())
    try:
        cached_args = env.cache_lookup(_CLI_ARGS_CACHE_KEY)
    except KeyError:
        cached_args = ()
    if not isinstance(cached_args, tuple):
        return list_to_chain(())
    normalized = tuple(item for item in cached_args if isinstance(item, str))
    return list_to_chain(Symbol(item) for item in normalized)


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
