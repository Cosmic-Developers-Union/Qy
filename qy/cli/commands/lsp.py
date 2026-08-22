# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""`qy lsp` 命令入口。.

目标：
- 承载 LSP 服务命令入口。
- 调用 `qy.tools.lsp` 提供的 public API。

禁止：
- 不得在 CLI 命令里定义 LSP 协议或服务语义。
"""

from __future__ import annotations

import click

from qy.cli import INSTALL_LSP_MESSAGE
from qy.cli._common import secho


def register(group: click.Group) -> None:
    """将 lsp 命令注册到给定的 click group。."""

    @group.command("lsp")
    @click.option("--stdio", is_flag=True, hidden=True)
    def lsp_command(stdio: bool) -> None:
        """Run the Qy language server."""
        try:
            from qy.tools.lsp import main as lsp_main
        except ModuleNotFoundError as e:
            if e.name in {"pygls", "lsprotocol"}:
                secho(INSTALL_LSP_MESSAGE, fg="red", err=True)
                raise click.exceptions.Exit(2) from e
            raise
        raise click.exceptions.Exit(lsp_main())
