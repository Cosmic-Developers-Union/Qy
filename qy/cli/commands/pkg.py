# coding: utf-8
"""qy pkg 子命令组。."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from qy.cli._common import secho

if TYPE_CHECKING:
    from qy.project.manifest import Manifest
    from qy.project.resolve import LocalManifestProvider


def create_pkg_app() -> click.Group:
    """创建 pkg 子命令组。."""

    @click.group("pkg", help="Package management commands.", no_args_is_help=True)
    def pkg_group() -> None:
        pass

    @pkg_group.command("init")
    @click.argument(
        "path",
        required=False,
        default=None,
    )
    def pkg_init(path: str | None) -> None:
        """Initialize a new qy package in the current directory."""
        cwd = Path.cwd()
        manifest_path = cwd / "qy.toml"
        if manifest_path.exists():
            secho("qy.toml already exists", fg="red", err=True)
            raise click.exceptions.Exit(1)

        if path is None:
            path = _infer_package_path(cwd)
            if path is None:
                path = click.prompt("Package path")

        from qy.project.manifest import Manifest
        from qy.project.manifest import serialize_manifest

        manifest = Manifest(pkg_path=path, version="0.1.0")
        manifest_path.write_text(serialize_manifest(manifest), encoding="utf-8")

        src_dir = cwd / "src"
        src_dir.mkdir(exist_ok=True)
        mod_file = src_dir / "mod.qy"
        if not mod_file.exists():
            mod_file.write_text(
                f"; {path} root module\n(module {_module_name(path)}\n  (exports))\n",
                encoding="utf-8",
            )

        secho(f"initialized package: {path}", fg="green")

    @pkg_group.command("add")
    @click.argument("dep_path")
    @click.option(
        "--version",
        "-v",
        default=None,
        help="Minimum version (default: latest).",
    )
    def pkg_add(dep_path: str, version: str | None) -> None:
        """Add a dependency to the current package."""
        manifest, manifest_path = _load_current_manifest()

        if version is None:
            version = "0.1.0"
            click.echo(f"no version specified, using {version}")

        from qy.project.manifest import Dependency
        from qy.project.manifest import Manifest
        from qy.project.manifest import serialize_manifest

        existing = {d.path: d for d in manifest.dependencies}
        existing[dep_path] = Dependency(path=dep_path, min_version=version)
        new_manifest = Manifest(
            pkg_path=manifest.pkg_path,
            version=manifest.version,
            description=manifest.description,
            license=manifest.license,
            authors=manifest.authors,
            entry=manifest.entry,
            src=manifest.src,
            export_modules=manifest.export_modules,
            dependencies=tuple(existing.values()),
            dev_dependencies=manifest.dev_dependencies,
            replaces=manifest.replaces,
        )
        manifest_path.write_text(serialize_manifest(new_manifest), encoding="utf-8")
        secho(f'added {dep_path} = "{version}"', fg="green")

    @pkg_group.command("remove")
    @click.argument("dep_path")
    def pkg_remove(dep_path: str) -> None:
        """Remove a dependency from the current package."""
        manifest, manifest_path = _load_current_manifest()
        from qy.project.manifest import Manifest
        from qy.project.manifest import serialize_manifest

        new_deps = tuple(d for d in manifest.dependencies if d.path != dep_path)
        if len(new_deps) == len(manifest.dependencies):
            secho(f"{dep_path} not found in dependencies", fg="yellow", err=True)
            raise click.exceptions.Exit(1)

        new_manifest = Manifest(
            pkg_path=manifest.pkg_path,
            version=manifest.version,
            description=manifest.description,
            license=manifest.license,
            authors=manifest.authors,
            entry=manifest.entry,
            src=manifest.src,
            export_modules=manifest.export_modules,
            dependencies=new_deps,
            dev_dependencies=manifest.dev_dependencies,
            replaces=manifest.replaces,
        )
        manifest_path.write_text(serialize_manifest(new_manifest), encoding="utf-8")
        secho(f"removed {dep_path}", fg="green")

    @pkg_group.command("update")
    @click.argument("dep_path", required=False, default=None)
    @click.option(
        "--version",
        "-v",
        default=None,
        help="New minimum version.",
    )
    def pkg_update(dep_path: str | None, version: str | None) -> None:
        """Update dependency version(s)."""
        manifest, manifest_path = _load_current_manifest()
        from qy.project.manifest import Dependency
        from qy.project.manifest import Manifest
        from qy.project.manifest import serialize_manifest

        if dep_path is None:
            secho(
                "updating all dependencies requires a registry backend, which is not implemented; "
                "pass a dependency path and --version instead",
                fg="red",
                err=True,
            )
            raise click.exceptions.Exit(2)

        if version is None:
            secho("--version required for targeted update", fg="red", err=True)
            raise click.exceptions.Exit(1)

        new_deps: list[Dependency] = []
        found = False
        for d in manifest.dependencies:
            if d.path == dep_path:
                new_deps.append(Dependency(path=d.path, min_version=version))
                found = True
            else:
                new_deps.append(d)

        if not found:
            secho(f"{dep_path} not found in dependencies", fg="yellow", err=True)
            raise click.exceptions.Exit(1)

        new_manifest = Manifest(
            pkg_path=manifest.pkg_path,
            version=manifest.version,
            description=manifest.description,
            license=manifest.license,
            authors=manifest.authors,
            entry=manifest.entry,
            src=manifest.src,
            export_modules=manifest.export_modules,
            dependencies=tuple(new_deps),
            dev_dependencies=manifest.dev_dependencies,
            replaces=manifest.replaces,
        )
        manifest_path.write_text(serialize_manifest(new_manifest), encoding="utf-8")
        secho(f"updated {dep_path} to {version}", fg="green")

    @pkg_group.command("graph")
    def pkg_graph() -> None:
        """Print the resolved dependency graph."""
        manifest, _ = _load_current_manifest()
        from qy.project.resolve import resolve

        provider = _build_provider_from_manifest(manifest)
        build_list = resolve(manifest, provider)

        click.echo(f"{manifest.pkg_path}@v{manifest.version}")
        for mod in build_list.modules:
            click.echo(f"  {mod.path}@v{mod.version}")

        if not build_list.modules:
            click.echo("  (no dependencies)")

    @pkg_group.command("verify")
    def pkg_verify() -> None:
        """Verify qy.sum integrity hashes."""
        cwd = Path.cwd()
        from qy.project.checksum import load_sum_file
        from qy.project.checksum import verify_package
        from qy.project.fetch import get_cached

        manifest, _ = _load_current_manifest()
        sum_file = load_sum_file(cwd / "qy.sum")

        all_ok = True
        for dep in manifest.dependencies:
            cached = get_cached(dep.path, dep.min_version)
            if cached is None:
                secho(f"  {dep.path}@v{dep.min_version}: not cached", fg="yellow")
                continue
            ok = verify_package(dep.path, dep.min_version, cached.root, sum_file)
            if ok:
                secho(f"  {dep.path}@v{dep.min_version}: ok", fg="green")
            else:
                secho(f"  {dep.path}@v{dep.min_version}: MISMATCH", fg="red")
                all_ok = False

        if not all_ok:
            raise click.exceptions.Exit(1)

    @pkg_group.command("build")
    def pkg_build() -> None:
        """Resolve dependencies and compile the package."""
        manifest, _ = _load_current_manifest()
        cwd = Path.cwd()
        src_dir = cwd / manifest.src

        if not src_dir.exists():
            secho(
                f"source directory {manifest.src}/ not found",
                fg="red",
                err=True,
            )
            raise click.exceptions.Exit(1)

        from qy.runtime import Qy

        qy = Qy()
        source_files = sorted(src_dir.rglob("*.qy"))
        errors = 0
        for f in source_files:
            try:
                qy.evaluate_file(f)
                click.echo(f"  compiled {f.relative_to(cwd)}")
            except Exception as e:
                secho(f"  error {f.relative_to(cwd)}: {e}", fg="red", err=True)
                errors += 1

        if errors:
            secho(f"\nbuild failed: {errors} error(s)", fg="red")
            raise click.exceptions.Exit(1)
        secho(f"\nbuild ok: {len(source_files)} module(s)", fg="green")

    @pkg_group.command("test")
    def pkg_test() -> None:
        """Run package tests."""
        _manifest, _ = _load_current_manifest()
        cwd = Path.cwd()
        test_dir = cwd / "test"

        if not test_dir.exists():
            secho("no test/ directory found", fg="yellow")
            return

        from qy.runtime import Qy

        test_files = sorted(test_dir.rglob("*_test.qy"))
        if not test_files:
            secho("no test files found (expected *_test.qy)", fg="yellow")
            return

        qy = Qy()
        passed = 0
        failed = 0
        for f in test_files:
            try:
                qy.evaluate_file(f)
                secho(f"  pass {f.relative_to(cwd)}", fg="green")
                passed += 1
            except Exception as e:
                secho(f"  fail {f.relative_to(cwd)}: {e}", fg="red", err=True)
                failed += 1

        click.echo(f"\n{passed} passed, {failed} failed")
        if failed:
            raise click.exceptions.Exit(1)

    @pkg_group.command("publish")
    def pkg_publish() -> None:
        """Validate the manifest and report the release path.

        There is no registry backend yet, so this command never claims success:
        it validates the manifest, prints the manual tagging command, and exits
        with code 2 (unsupported operation).
        """
        manifest, _ = _load_current_manifest()

        if not manifest.pkg_path:
            secho("package path is required for publishing", fg="red", err=True)
            raise click.exceptions.Exit(1)
        if not manifest.version:
            secho("version is required for publishing", fg="red", err=True)
            raise click.exceptions.Exit(1)

        click.echo(f"package: {manifest.pkg_path}@v{manifest.version}")
        secho(
            "publish is not implemented: no registry backend.",
            fg="red",
            err=True,
        )
        secho(
            f"create a release tag manually: git tag v{manifest.version} && git push --tags",
            fg="yellow",
            err=True,
        )
        raise click.exceptions.Exit(2)

    return pkg_group


def _load_current_manifest() -> tuple[Manifest, Path]:
    """加载当前目录的 qy.toml。."""
    from qy.cli._common import secho
    from qy.project.manifest import parse_manifest_file

    cwd = Path.cwd()
    manifest_path = cwd / "qy.toml"
    if not manifest_path.exists():
        secho("no qy.toml in current directory", fg="red", err=True)
        raise click.exceptions.Exit(1)
    return parse_manifest_file(manifest_path), manifest_path


def _infer_package_path(cwd: Path) -> str | None:
    """尝试从 git remote 推断包路径。."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            return _git_url_to_package_path(url)
    except FileNotFoundError:
        pass
    return None


def _git_url_to_package_path(url: str) -> str:
    """将 git URL 转换为包路径。."""
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("https://"):
        return url[8:]
    if url.startswith("http://"):
        return url[7:]
    if ":" in url and "@" in url:
        # git@github.com:user/repo
        _, rest = url.split(":", 1)
        host = url.split("@")[1].split(":")[0]
        return f"{host}/{rest}"
    return url


def _module_name(pkg_path: str) -> str:
    """从包路径提取模块名。."""
    parts = pkg_path.split("/")
    return parts[-1] if parts else pkg_path


def _build_provider_from_manifest(manifest: Manifest) -> LocalManifestProvider:
    """从当前清单构建 LocalManifestProvider（仅包含直接依赖）。."""
    from qy.project.fetch import get_cached
    from qy.project.manifest import parse_manifest_file
    from qy.project.resolve import LocalManifestProvider

    provider = LocalManifestProvider()
    cwd = Path.cwd()

    for dep in manifest.dependencies:
        for r in manifest.replaces:
            if r.path == dep.path:
                local = (cwd / r.local_path).resolve()
                local_manifest = local / "qy.toml"
                if local_manifest.exists():
                    provider.register(parse_manifest_file(local_manifest))
                break
        else:
            cached = get_cached(dep.path, dep.min_version)
            if cached is not None:
                cached_manifest = cached.root / "qy.toml"
                if cached_manifest.exists():
                    provider.register(parse_manifest_file(cached_manifest))

    return provider
