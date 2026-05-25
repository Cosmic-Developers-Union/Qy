# coding: utf-8
"""qy.sum 完整性校验。."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChecksumEntry:
    """qy.sum 中的一条记录。."""

    path: str
    version: str
    suffix: str
    hash: str

    def to_line(self) -> str:
        key = f"{self.path} v{self.version}"
        if self.suffix:
            key += f"/{self.suffix}"
        return f"{key} h1:{self.hash}"


@dataclass
class ChecksumFile:
    """qy.sum 文件的完整表示。."""

    entries: list[ChecksumEntry]

    def lookup(self, path: str, version: str, suffix: str = "") -> str | None:
        for e in self.entries:
            if e.path == path and e.version == version and e.suffix == suffix:
                return e.hash
        return None

    def add(self, path: str, version: str, suffix: str, hash_value: str) -> None:
        for i, e in enumerate(self.entries):
            if e.path == path and e.version == version and e.suffix == suffix:
                self.entries[i] = ChecksumEntry(path, version, suffix, hash_value)
                return
        self.entries.append(ChecksumEntry(path, version, suffix, hash_value))
        self.entries.sort(key=lambda e: (e.path, e.version, e.suffix))

    def remove(self, path: str) -> None:
        self.entries = [e for e in self.entries if e.path != path]


def parse_sum_file(content: str) -> ChecksumFile:
    """解析 qy.sum 内容。."""
    entries: list[ChecksumEntry] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry = _parse_sum_line(line)
        if entry is not None:
            entries.append(entry)
    return ChecksumFile(entries=entries)


def load_sum_file(path: Path) -> ChecksumFile:
    """加载 qy.sum，不存在返回空。."""
    if not path.exists():
        return ChecksumFile(entries=[])
    return parse_sum_file(path.read_text(encoding="utf-8"))


def save_sum_file(path: Path, checksums: ChecksumFile) -> None:
    """保存 qy.sum。."""
    lines = [e.to_line() for e in checksums.entries]
    path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def hash_directory(directory: Path) -> str:
    """计算目录内所有文件的聚合哈希。."""
    h = hashlib.sha256()
    for file in sorted(directory.rglob("*")):
        if file.is_file():
            rel = file.relative_to(directory)
            h.update(str(rel).encode())
            h.update(file.read_bytes())
    return h.hexdigest()


def hash_file(path: Path) -> str:
    """计算单个文件的哈希。."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_package(pkg_path: str, version: str, pkg_root: Path, checksums: ChecksumFile) -> bool:
    """验证包目录的哈希与 qy.sum 记录一致。."""
    expected = checksums.lookup(pkg_path, version, "src")
    if expected is None:
        return True
    src_dir = pkg_root / "src"
    if not src_dir.exists():
        return False
    actual = hash_directory(src_dir)
    return actual == expected


def _parse_sum_line(line: str) -> ChecksumEntry | None:
    """解析一行 qy.sum。格式：path version[/suffix] h1:hash."""
    parts = line.split()
    if len(parts) < 3:
        return None

    path = parts[0]
    version_part = parts[1]
    hash_part = parts[2]

    suffix = ""
    if "/" in version_part:
        version_str, suffix = version_part.rsplit("/", 1)
    else:
        version_str = version_part

    version = version_str.lstrip("v")

    if hash_part.startswith("h1:"):
        hash_value = hash_part[3:]
    else:
        hash_value = hash_part

    return ChecksumEntry(path=path, version=version, suffix=suffix, hash=hash_value)
