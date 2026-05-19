# coding: utf-8
# QY_DELETE_AFTER_MIGRATION: target=qy/frontend/reader.py
"""Qy Reader re-export shim.

所有 reader 功能已迁移到 qy/frontend/reader.py。
本文件保留用于向后兼容，请使用 from qy.frontend.reader import ... 或 from qy.reader import ...
"""

from __future__ import annotations

from qy.frontend.reader import *  # noqa: F401, F403
from qy.frontend.reader import __all__  # noqa: F401