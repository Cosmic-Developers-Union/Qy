# -*- coding: utf-8 -*-

"""`qy operators` 命令入口。."""

from __future__ import annotations

import click

from qy.symbol_space.profile import format_operator_docs


def register(group: click.Group) -> None:
    """将 operators 命令注册到给定的 click group。."""

    @group.command("operators")
    def operators_command() -> None:
        """列出当前标准库支持的算子."""
        click.echo(format_operator_docs(), nl=False)
