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

from typing import Any

import typer


def register(app: Any) -> None:
    """将 lsp 命令注册到给定的 typer 应用。."""
    from qy.cli import INSTALL_LSP_MESSAGE

    @app.command("lsp")
    def lsp_command(stdio: bool = typer.Option(False, "--stdio", hidden=True)) -> None:
        try:
            from qy.tools.lsp import main as lsp_main
        except ModuleNotFoundError as e:
            if e.name in {"pygls", "lsprotocol"}:
                typer.secho(INSTALL_LSP_MESSAGE, fg=typer.colors.RED, err=True)
                raise typer.Exit(2) from e
            raise
        raise typer.Exit(lsp_main())
