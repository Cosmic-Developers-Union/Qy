# coding: utf-8
"""qy.toml 清单解析与数据模型。."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Dependency:
    """一个依赖项：路径 + 最低版本。."""

    path: str
    min_version: str


@dataclass(frozen=True, slots=True)
class ReplaceDef:
    """依赖替换：指向本地路径。."""

    path: str
    local_path: str


@dataclass(frozen=True, slots=True)
class Manifest:
    """qy.toml 的完整表示。."""

    # [package]
    pkg_path: str
    version: str
    description: str = ""
    license: str = ""
    authors: tuple[str, ...] = ()
    entry: str | None = None
    src: str = "src"

    # [exports]
    export_modules: tuple[str, ...] | None = None

    # [dependencies]
    dependencies: tuple[Dependency, ...] = ()

    # [dev-dependencies]
    dev_dependencies: tuple[Dependency, ...] = ()

    # [replace]
    replaces: tuple[ReplaceDef, ...] = ()

    @property
    def is_executable(self) -> bool:
        return self.entry is not None


@dataclass(frozen=True, slots=True)
class WorkspaceManifest:
    """qy-workspace.toml 的表示。."""

    members: tuple[str, ...] = ()


def parse_manifest(content: str) -> Manifest:
    """从 TOML 字符串解析 Manifest。."""
    data = tomllib.loads(content)
    return _build_manifest(data)


def parse_manifest_file(path: Path) -> Manifest:
    """从文件路径解析 Manifest。."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return _build_manifest(data)


def parse_workspace_file(path: Path) -> WorkspaceManifest:
    """解析 qy-workspace.toml。."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    ws = data.get("workspace", {})
    members = tuple(ws.get("members", []))
    return WorkspaceManifest(members=members)


def _build_manifest(data: dict[str, Any]) -> Manifest:
    pkg = data.get("package", {})
    pkg_path = pkg.get("path", "")
    version = pkg.get("version", "0.0.0")
    description = pkg.get("description", "")
    license_ = pkg.get("license", "")
    authors = tuple(pkg.get("authors", []))
    entry = pkg.get("entry")
    src = pkg.get("src", "src")

    exports_section = data.get("exports", {})
    export_modules: tuple[str, ...] | None = None
    if "modules" in exports_section:
        export_modules = tuple(exports_section["modules"])

    deps = _parse_deps(data.get("dependencies", {}))
    dev_deps = _parse_deps(data.get("dev-dependencies", {}))
    replaces = _parse_replaces(data.get("replace", {}))

    return Manifest(
        pkg_path=pkg_path,
        version=version,
        description=description,
        license=license_,
        authors=authors,
        entry=entry,
        src=src,
        export_modules=export_modules,
        dependencies=deps,
        dev_dependencies=dev_deps,
        replaces=replaces,
    )


def _parse_deps(deps_data: dict[str, Any]) -> tuple[Dependency, ...]:
    result: list[Dependency] = []
    for path, version in deps_data.items():
        if isinstance(version, str):
            result.append(Dependency(path=path, min_version=version))
    return tuple(result)


def _parse_replaces(replace_data: dict[str, Any]) -> tuple[ReplaceDef, ...]:
    result: list[ReplaceDef] = []
    for pkg_path, value in replace_data.items():
        if isinstance(value, dict) and "path" in value:
            result.append(ReplaceDef(path=pkg_path, local_path=value["path"]))
    return tuple(result)


def serialize_manifest(manifest: Manifest) -> str:
    """将 Manifest 序列化为 TOML 字符串。."""
    lines: list[str] = []

    lines.append("[package]")
    lines.append(f'path = "{manifest.pkg_path}"')
    lines.append(f'version = "{manifest.version}"')
    if manifest.description:
        lines.append(f'description = "{manifest.description}"')
    if manifest.license:
        lines.append(f'license = "{manifest.license}"')
    if manifest.authors:
        authors_str = ", ".join(f'"{a}"' for a in manifest.authors)
        lines.append(f"authors = [{authors_str}]")
    if manifest.entry:
        lines.append(f'entry = "{manifest.entry}"')
    if manifest.src != "src":
        lines.append(f'src = "{manifest.src}"')

    if manifest.export_modules is not None:
        lines.append("")
        lines.append("[exports]")
        mods_str = ", ".join(f'"{m}"' for m in manifest.export_modules)
        lines.append(f"modules = [{mods_str}]")

    if manifest.dependencies:
        lines.append("")
        lines.append("[dependencies]")
        for dep in manifest.dependencies:
            lines.append(f'"{dep.path}" = "{dep.min_version}"')

    if manifest.dev_dependencies:
        lines.append("")
        lines.append("[dev-dependencies]")
        for dep in manifest.dev_dependencies:
            lines.append(f'"{dep.path}" = "{dep.min_version}"')

    if manifest.replaces:
        lines.append("")
        lines.append("[replace]")
        for r in manifest.replaces:
            lines.append(f'"{r.path}" = {{ path = "{r.local_path}" }}')

    lines.append("")
    return "\n".join(lines)
