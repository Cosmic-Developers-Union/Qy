# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""`qy fmt` 命令入口。.

目标：
- 承载格式化命令入口。
- 调用 `qy.tools.fmt` 提供的 public API。

禁止：
- 不得在 CLI 命令里定义 formatter 语义。
"""

from __future__ import annotations

from pathlib import Path

import click

from qy.cli._common import read_debug_source
from qy.cli._common import secho
from qy.frontend.reader import ReaderSyntaxError
from qy.tools.fmt import format_source


def register(group: click.Group) -> None:
    """将 fmt 命令注册到给定的 click group。."""

    @group.command("fmt")
    @click.argument("path", type=str)
    @click.option(
        "--write",
        "-w",
        is_flag=True,
        help="Rewrite the file in place.",
    )
    def format_command(path: str, write: bool) -> None:
        """Format Qy source code with syntax checking. Use '-' for stdin."""
        if write and path == "-":
            secho("fmt: cannot --write to stdin", fg="red", err=True)
            raise click.exceptions.Exit(2)
        source, source_name = read_debug_source(path)
        try:
            formatted = format_source(source)
            if write:
                target = Path(path)
                target.write_text(formatted, encoding="utf-8")
                secho(f"formatted {target}", fg="green")
                return
            click.echo(formatted, nl=False)
        except ReaderSyntaxError as e:
            secho(f"{source_name}: syntax error: {e}", fg="red", err=True)
            raise click.exceptions.Exit(1) from e
        except OSError as e:
            secho(f"{source_name}: {e}", fg="red", err=True)
            raise click.exceptions.Exit(1) from e
