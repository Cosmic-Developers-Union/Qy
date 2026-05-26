# -*- coding: utf-8 -*-

"""`qy operators` 命令入口。."""

from __future__ import annotations

from typing import Any

import typer

from qy.symbol_space.profile import format_operator_docs


def register(app: Any) -> None:
    """将 operators 命令注册到给定的 typer 应用。."""

    @app.command("operators")
    def operators_command() -> None:
        """列出当前标准库支持的算子."""
        typer.echo(format_operator_docs(), nl=False)
