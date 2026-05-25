# coding: utf-8
"""包获取与本地缓存管理。."""

from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def qy_home() -> Path:
    """获取 QY_HOME 路径。."""
    env = os.environ.get("QY_HOME")
    if env:
        return Path(env)
    return Path.home() / ".qy"


def pkg_cache_dir() -> Path:
    return qy_home() / "pkg"


def download_cache_dir() -> Path:
    return pkg_cache_dir() / "download"


def mod_cache_dir() -> Path:
    return pkg_cache_dir() / "mod"


def build_cache_dir() -> Path:
    return qy_home() / "build" / "cache"


@dataclass(frozen=True, slots=True)
class CachedPackage:
    """本地缓存中的一个包。."""

    path: str
    version: str
    root: Path

    @property
    def src_dir(self) -> Path:
        from qy.project.manifest import parse_manifest_file

        manifest_path = self.root / "qy.toml"
        if manifest_path.exists():
            manifest = parse_manifest_file(manifest_path)
            return self.root / manifest.src
        return self.root / "src"


def cached_package_dir(pkg_path: str, version: str) -> Path:
    """包在 mod cache 中的目录。."""
    return mod_cache_dir() / f"{pkg_path}@v{version}"


def is_cached(pkg_path: str, version: str) -> bool:
    """检查包是否已在本地缓存。."""
    d = cached_package_dir(pkg_path, version)
    return d.exists() and (d / "qy.toml").exists()


def get_cached(pkg_path: str, version: str) -> CachedPackage | None:
    """获取缓存中的包，不存在返回 None。."""
    if not is_cached(pkg_path, version):
        return None
    return CachedPackage(
        path=pkg_path,
        version=version,
        root=cached_package_dir(pkg_path, version),
    )


def cache_from_local(pkg_path: str, version: str, source_dir: Path) -> CachedPackage:
    """从本地目录缓存包（用于 [replace] 场景不复制，直接指向）。."""
    return CachedPackage(path=pkg_path, version=version, root=source_dir)


def cache_from_archive(pkg_path: str, version: str, archive_path: Path) -> CachedPackage:
    """从 zip 存档解压到 mod cache。."""
    target = cached_package_dir(pkg_path, version)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(target)

    return CachedPackage(path=pkg_path, version=version, root=target)


def fetch_package(pkg_path: str, version: str) -> CachedPackage:
    """获取包：先查缓存，未命中则下载。.

    当前实现仅支持 git-hosted 包（github.com 等）。
    下载策略：尝试从 git tag 获取 zip archive。
    """
    cached = get_cached(pkg_path, version)
    if cached is not None:
        return cached

    archive_path = _download_archive(pkg_path, version)
    return cache_from_archive(pkg_path, version, archive_path)


def _download_archive(pkg_path: str, version: str) -> Path:
    """下载包的源码存档。."""
    parts = pkg_path.split("/")
    if len(parts) < 3:
        msg = f"cannot determine download URL for package: {pkg_path}"
        raise ValueError(msg)

    domain = parts[0]
    owner = parts[1]
    repo = parts[2]

    if domain == "github.com":
        url = f"https://github.com/{owner}/{repo}/archive/refs/tags/v{version}.zip"
    elif domain == "gitlab.com":
        url = f"https://gitlab.com/{owner}/{repo}/-/archive/v{version}/{repo}-v{version}.zip"
    else:
        url = f"https://{domain}/{owner}/{repo}/archive/v{version}.zip"

    dl_dir = download_cache_dir() / pkg_path / "@v"
    dl_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dl_dir / f"v{version}.zip"

    if not archive_path.exists():
        try:
            with urlopen(url) as resp, open(archive_path, "wb") as f:
                shutil.copyfileobj(resp, f)
        except URLError as e:
            msg = f"failed to download {pkg_path}@v{version} from {url}: {e}"
            raise RuntimeError(msg) from e

    return archive_path


def clear_cache(pkg_path: str | None = None, version: str | None = None) -> None:
    """清除缓存。."""
    if pkg_path is None:
        cache = mod_cache_dir()
        if cache.exists():
            shutil.rmtree(cache)
        return

    if version is None:
        pattern = f"{pkg_path}@v*"
        cache = mod_cache_dir()
        if cache.exists():
            for d in cache.glob(pattern):
                shutil.rmtree(d)
    else:
        d = cached_package_dir(pkg_path, version)
        if d.exists():
            shutil.rmtree(d)
