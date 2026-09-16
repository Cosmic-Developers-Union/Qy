# -*- coding: utf-8 -*-

from typing import Any

import click

from qy.cli._common import REPL_COMMANDS as REPL_COMMANDS

INSTALL_LSP_MESSAGE = (
    "Qy LSP requires the optional lsp dependency. Install with: pip install 'QyLang[lsp]'"
)


def main() -> int:
    from qy.cli._app import build_cli

    cli = build_cli()
    try:
        result = cli(standalone_mode=False)
    except click.exceptions.Exit as e:
        return e.exit_code
    except click.exceptions.Abort:
        return 1
    except click.UsageError as e:
        # non-standalone 模式下 click 不会自行打印用法错误；这里补上，
        # 避免参数错误以裸 traceback 形式抛给用户。
        e.show()
        return e.exit_code
    except click.ClickException as e:
        e.show()
        return e.exit_code
    # click 在 non-standalone 模式下会把命令显式 raise 的 Exit(rc) 转成返回值；
    # 若直接忽略该返回值，`qy run bad.qy` 这类失败会错误地以 0 退出。
    if isinstance(result, int):
        return result
    return 0


def create_app() -> Any:
    """Return the top-level click group for tests and tooling."""
    from qy.cli._app import build_cli

    return build_cli()


# Re-export for external consumers (tests, benchmark CLI, etc.)
def _repl_completions(qy: Any, text: str) -> list[str]:
    from qy.cli.commands.repl import _repl_completions as _impl

    return _impl(qy, text)
