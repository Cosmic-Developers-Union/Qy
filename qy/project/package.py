# coding: utf-8
"""Qy 包身份与结构模型。."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from qy.project.manifest import Manifest
from qy.project.manifest import parse_manifest_file

_DOMAIN_PATTERN = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$")


@dataclass(frozen=True, slots=True)
class PackageId:
    """包的全局唯一标识。."""

    path: str
    version: str

    def __str__(self) -> str:
        return f"{self.path}@v{self.version}"

    @property
    def domain(self) -> str:
        parts = self.path.split("/")
        return parts[0] if parts else ""

    @property
    def repo_path(self) -> str:
        parts = self.path.split("/")
        return "/".join(parts[:3]) if len(parts) >= 3 else self.path


@dataclass(frozen=True, slots=True)
class Package:
    """一个已解析的包实例。."""

    id: PackageId
    root: Path
    manifest: Manifest

    @property
    def src_dir(self) -> Path:
        return self.root / self.manifest.src

    @property
    def root_module_path(self) -> Path:
        return self.src_dir / "mod.qy"

    @property
    def test_dir(self) -> Path:
        return self.root / "test"

    def resolve_submodule(self, submodule: str) -> Path | None:
        """将子模块名解析为磁盘路径。."""
        parts = submodule.split("/")
        candidate = self.src_dir / "/".join(parts[:-1]) / f"{parts[-1]}.qy"
        if candidate.exists():
            return candidate
        dir_candidate = self.src_dir / "/".join(parts) / "mod.qy"
        if dir_candidate.exists():
            return dir_candidate
        return None

    def is_exported(self, submodule: str) -> bool:
        """检查子模块是否对外可见。."""
        if submodule.startswith("internal/") or "/internal/" in submodule:
            return False
        if self.manifest.export_modules is None:
            return True
        return submodule in self.manifest.export_modules

    def list_modules(self) -> list[str]:
        """列出包内所有模块（相对路径）。."""
        modules: list[str] = []
        src = self.src_dir
        if not src.exists():
            return modules
        for qy_file in src.rglob("*.qy"):
            rel = qy_file.relative_to(src)
            parts = list(rel.parts)
            if parts[-1] == "mod.qy":
                if len(parts) == 1:
                    continue
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1].removesuffix(".qy")
            modules.append("/".join(parts))
        return sorted(modules)


def load_package(root: Path) -> Package:
    """从目录加载包。."""
    manifest_path = root / "qy.toml"
    if not manifest_path.exists():
        msg = f"no qy.toml found in {root}"
        raise FileNotFoundError(msg)
    manifest = parse_manifest_file(manifest_path)
    pkg_id = PackageId(path=manifest.pkg_path, version=manifest.version)
    return Package(id=pkg_id, root=root, manifest=manifest)


def is_package_path(name: str) -> bool:
    """判断模块名是否为包路径（含域名前缀）。."""
    if "/" not in name:
        return False
    domain = name.split("/")[0]
    return bool(_DOMAIN_PATTERN.match(domain))


def split_package_module(name: str, known_packages: set[str]) -> tuple[str, str]:
    """从完整模块路径中分离包路径和子模块路径。.

    使用最长前缀匹配在已知包集合中查找。
    """
    parts = name.split("/")
    for i in range(len(parts), 0, -1):
        candidate = "/".join(parts[:i])
        if candidate in known_packages:
            submodule = "/".join(parts[i:])
            return candidate, submodule
    return name, ""
