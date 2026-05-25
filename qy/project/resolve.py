# coding: utf-8
"""Minimum Version Selection (MVS) 依赖解析器。.

Go 风格的确定性版本解析：对每个依赖取所有要求中的最大最小版本。
无 SAT solver，无回溯，O(n)。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Protocol

from qy.project.manifest import Manifest


@dataclass(frozen=True, slots=True)
class ResolvedModule:
    """解析结果中的一个模块。."""

    path: str
    version: str


@dataclass(frozen=True, slots=True)
class BuildList:
    """MVS 解析产出的完整构建列表。."""

    modules: tuple[ResolvedModule, ...]

    def get(self, path: str) -> ResolvedModule | None:
        for m in self.modules:
            if m.path == path:
                return m
        return None

    def paths(self) -> set[str]:
        return {m.path for m in self.modules}

    def as_dict(self) -> dict[str, str]:
        return {m.path: m.version for m in self.modules}


class ManifestProvider(Protocol):
    """获取指定包版本的清单。."""

    def get_manifest(self, path: str, version: str) -> Manifest | None: ...


def compare_versions(a: str, b: str) -> int:
    """比较两个 semver 版本字符串。返回 -1, 0, 1。."""
    pa = _parse_version(a)
    pb = _parse_version(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def max_version(a: str, b: str) -> str:
    """返回两个版本中较大的。."""
    if compare_versions(a, b) >= 0:
        return a
    return b


def resolve(root: Manifest, provider: ManifestProvider) -> BuildList:
    """执行 MVS 解析。.

    从 root manifest 出发，递归收集所有传递依赖的最低版本要求，
    对每个 module-path 取 max(所有最低版本)。
    """
    requirements: dict[str, str] = {}
    visited: set[tuple[str, str]] = set()

    _collect_requirements(root, provider, requirements, visited)

    modules = tuple(
        ResolvedModule(path=path, version=version) for path, version in sorted(requirements.items())
    )
    return BuildList(modules=modules)


def _collect_requirements(
    manifest: Manifest,
    provider: ManifestProvider,
    requirements: dict[str, str],
    visited: set[tuple[str, str]],
) -> None:
    """递归收集所有依赖的版本要求。."""
    for dep in manifest.dependencies:
        current = requirements.get(dep.path)
        selected = dep.min_version if current is None else max_version(current, dep.min_version)
        requirements[dep.path] = selected

        key = (dep.path, selected)
        if key in visited:
            continue
        visited.add(key)

        dep_manifest = provider.get_manifest(dep.path, selected)
        if dep_manifest is not None:
            _collect_requirements(dep_manifest, provider, requirements, visited)


def _parse_version(v: str) -> tuple[int, ...]:
    """将版本字符串解析为可比较的元组。."""
    parts: list[int] = []
    for segment in v.split("."):
        numeric = ""
        for ch in segment:
            if ch.isdigit():
                numeric += ch
            else:
                break
        parts.append(int(numeric) if numeric else 0)
    return tuple(parts)


@dataclass
class LocalManifestProvider:
    """从本地缓存目录读取清单的 provider。."""

    manifests: dict[tuple[str, str], Manifest] = field(default_factory=dict)

    def register(self, manifest: Manifest) -> None:
        self.manifests[(manifest.pkg_path, manifest.version)] = manifest

    def get_manifest(self, path: str, version: str) -> Manifest | None:
        return self.manifests.get((path, version))
