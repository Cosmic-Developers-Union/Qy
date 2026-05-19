# coding: utf-8
# QY_DELETE_AFTER_SEMANTIC_REPLACEMENT: target=qy/std/*

from __future__ import annotations

from pathlib import Path

from qy.environment import Environment
from qy.operators import ScopeOperator
from qy.reader import Symbol
from qy.runtime import Qy
from qy.stdlib.module import StandardModule
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import list_to_qy_cons

_CLI_ARGS_CACHE_KEY = ("qy", "cli_args")


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
        },
    )


def set_cli_args(env: Environment, args: tuple[str, ...]) -> None:
    env.cache_define(_CLI_ARGS_CACHE_KEY, tuple(args))


def _cli_args(args: tuple[object, ...], env: Environment) -> object:
    if args:
        return list_to_qy_cons(())
    try:
        cached_args = env.cache_lookup(_CLI_ARGS_CACHE_KEY)
    except KeyError:
        cached_args = ()
    if not isinstance(cached_args, tuple):
        return list_to_qy_cons(())
    normalized = tuple(item for item in cached_args if isinstance(item, str))
    return list_to_qy_cons(Symbol(item) for item in normalized)


def _list_dir(args: tuple[object, ...], env: Environment) -> object:
    del env
    if len(args) != 1:
        return list_to_qy_cons(())
    path_value = args[0]
    path = Path(_as_text(path_value)).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.is_dir():
        return list_to_qy_cons(())
    entries = tuple(
        Symbol(item.name) for item in sorted(path.iterdir(), key=lambda item: item.name)
    )
    return list_to_qy_cons(entries)


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
        qy = Qy()
        result = await qy.evaluate_file_async(path)
        # Any non-nil result means the file ran successfully
        return QY_T if result is not QY_NIL else QY_NIL
    except Exception:
        return QY_NIL


def _as_text(value: object) -> str:
    if isinstance(value, Symbol):
        return value.name
    return str(value)
