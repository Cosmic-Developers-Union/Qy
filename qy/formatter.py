# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/tools/fmt/*
"""Qy Formatter re-export shim.

所有 formatter 功能已迁移到 qy/tools/fmt/。
本文件保留用于向后兼容，请使用 from qy.tools.fmt import ... 或 from qy.formatter import ...
"""

from __future__ import annotations

from qy.tools.fmt import *  # noqa: F403
from qy.tools.fmt import __all__  # noqa: F401
