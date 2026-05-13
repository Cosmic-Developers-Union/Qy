# coding: utf-8

"""Token analysis script — count tokens in project source files using tiktoken."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tiktoken

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXCLUDED_DIRS = {
    "__pycache__",
    "node_modules",
    "dist",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    ".env",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".claude",
    "site-packages",
    ".eggs",
    "*.egg-info",
}

DEFAULT_EXTENSIONS = {
    ".py",
    ".qy",
    ".ts",
    ".js",
    ".json",
    ".toml",
    ".md",
    ".yaml",
    ".yml",
}

DEFAULT_ENCODING = "o200k_base"

# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


def count_tokens(text: str, enc: tiktoken.Encoding) -> int:
    return len(enc.encode(text))


def scan_files(root: Path, extensions: set[str]) -> list[Path]:
    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in extensions:
            results.append(path)
    return sorted(results)


# ---------------------------------------------------------------------------
# Tree building
# ---------------------------------------------------------------------------


class TreeNode:
    __slots__ = ("children", "is_dir", "name", "tokens")

    def __init__(self, name: str, is_dir: bool = False) -> None:
        self.name = name
        self.tokens: int = 0
        self.children: list[TreeNode] = []
        self.is_dir = is_dir


def build_tree(root_path: Path, files: list[Path], enc: tiktoken.Encoding) -> TreeNode:
    root = TreeNode(root_path.name or ".", is_dir=True)

    for fpath in files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tokens = count_tokens(text, enc)

        rel = fpath.relative_to(root_path)
        node = root
        for part in rel.parts[:-1]:
            child = _find_or_create_child(node, part, is_dir=True)
            node = child
        leaf = _find_or_create_child(node, rel.parts[-1], is_dir=False)
        leaf.tokens = tokens

    _aggregate_tokens(root)
    return root


def _find_or_create_child(parent: TreeNode, name: str, *, is_dir: bool) -> TreeNode:
    for child in parent.children:
        if child.name == name and child.is_dir == is_dir:
            return child
    node = TreeNode(name, is_dir=is_dir)
    parent.children.append(node)
    return node


def _aggregate_tokens(node: TreeNode) -> int:
    if not node.children:
        return node.tokens
    total = sum(_aggregate_tokens(child) for child in node.children)
    node.tokens = total
    return total


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

UNITS = [
    (1_000_000_000, "B"),
    (1_000_000, "M"),
    (1_000, "K"),
]

SIZE_MARKERS = [
    (2048, "···"),  # ≤ 2K: 极为舒适
    (4096, "·--"),  # ≤ 4K: 标准
    (8192, "---"),  # ≤ 8K: 较为困难
]


def _size_mark(n: int) -> str:
    for threshold, mark in SIZE_MARKERS:
        if n <= threshold:
            return mark
    return "XXX"  # > 8K: 需要拆分


def _fmt_tokens(n: int) -> str:
    if n >= 1_000:
        return f"{n:,}"
    return str(n)


def _sort_key_tokens(node: TreeNode) -> int:
    return -node.tokens


def _sort_key_name(node: TreeNode) -> str:
    return node.name


def render_tree(
    node: TreeNode,
    *,
    sort_key=_sort_key_tokens,
    prefix: str = "",
    is_last: bool = True,
    is_root: bool = True,
    top: bool = True,
) -> list[str]:
    lines: list[str] = []

    node.children.sort(key=sort_key)

    if is_root:
        lines.append(f"{node.name}/")
    else:
        connector = "└── " if is_last else "├── "
        suffix = "/" if node.is_dir else ""
        token_str = _fmt_tokens(node.tokens).rjust(10)
        mark = _size_mark(node.tokens) if not node.is_dir else ""
        lines.append(f"{prefix}{connector}{node.name}{suffix}  {token_str} tokens {mark}")

    child_prefix = prefix + ("    " if is_last or is_root else "│   ")
    for i, child in enumerate(node.children):
        last = i == len(node.children) - 1
        lines.extend(
            render_tree(
                child,
                sort_key=sort_key,
                prefix=child_prefix if not is_root else "",
                is_last=last,
                is_root=False,
                top=False,
            )
        )

    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count tokens in project source files.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="qy",
        help="Project root directory (default: qy).",
    )
    parser.add_argument(
        "-e",
        "--encoding",
        default=DEFAULT_ENCODING,
        help=f"tiktoken encoding name (default: {DEFAULT_ENCODING}).",
    )
    parser.add_argument(
        "-s",
        "--sort",
        choices=["tokens", "name"],
        default="tokens",
        help="Sort order (default: tokens).",
    )
    parser.add_argument(
        "--ext",
        nargs="*",
        help="File extensions to include (e.g. .py .ts). Default: common source files.",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: {args.path} is not a directory", file=sys.stderr)
        sys.exit(1)

    extensions = set(args.ext) if args.ext else DEFAULT_EXTENSIONS
    sort_key = _sort_key_name if args.sort == "name" else _sort_key_tokens

    try:
        enc = tiktoken.get_encoding(args.encoding)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    files = scan_files(root, extensions)
    if not files:
        print("No matching files found.", file=sys.stderr)
        sys.exit(0)

    tree = build_tree(root, files, enc)

    lines = render_tree(tree, sort_key=sort_key)

    # Summary line
    total_tokens = tree.tokens
    sep = "─" * 50
    lines.append(sep)
    lines.append(f"Total: {_fmt_tokens(total_tokens)} tokens ({len(files)} files)")
    lines.append("")
    lines.append("Marker legend:")
    lines.append("  ···  ≤ 2,048 tokens  极为舒适")
    lines.append("  ·--  ≤ 4,096 tokens  标准")
    lines.append("  ---  ≤ 8,192 tokens  较为困难")
    lines.append("  XXX  > 8,192 tokens  需要拆分")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
