# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Any

import click

from qy.cli._common import CLI_COMMANDS as CLI_COMMANDS
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
    # click 在 non-standalone 模式下会把命令显式 raise 的 Exit(rc) 转成返回值；
    # 若直接忽略该返回值，`qy run bad.qy` 这类失败会错误地以 0 退出。
    if isinstance(result, int):
        return result
    return 0


def create_app() -> Any:
    """Return the top-level click group for tests and tooling."""
    from qy.cli._app import build_cli

    return build_cli()


class _QyGroupFallback(click.Group):
    """Backward-compatible alias retained for older imports/tests."""

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            if args and not args[0].startswith("-") and Path(args[0]).is_file():
                command = self.get_command(ctx, "run")
                if command is not None:
                    return "run", command, args
            raise


# Re-export for external consumers (tests, benchmark CLI, etc.)
def _repl_completions(qy: Any, text: str) -> list[str]:
    from qy.cli.commands.repl import _repl_completions as _impl

    return _impl(qy, text)
