# coding: utf-8
"""Tests for qy.project — manifest, package, resolve, fetch, checksum."""

from __future__ import annotations

from pathlib import Path

# ─── Manifest ───────────────────────────────────────────────────────────────


class TestManifestParsing:
    def test_parse_minimal(self):
        from qy.project.manifest import parse_manifest

        m = parse_manifest('[package]\npath = "github.com/user/hello"\nversion = "1.0.0"\n')
        assert m.pkg_path == "github.com/user/hello"
        assert m.version == "1.0.0"
        assert m.src == "src"
        assert m.dependencies == ()
        assert m.export_modules is None

    def test_parse_full(self):
        from qy.project.manifest import parse_manifest

        toml = """\
[package]
path = "github.com/user/qy-json"
version = "0.3.1"
description = "JSON parser"
license = "MIT"
authors = ["Alice <a@b.com>"]
entry = "src/main.qy"
src = "lib"

[exports]
modules = ["json", "json.parse"]

[dependencies]
"github.com/user/qy-strings" = "0.2.0"
"github.com/user/qy-io" = "1.0.0"

[dev-dependencies]
"github.com/user/qy-testkit" = "0.1.0"

[replace]
"github.com/user/qy-strings" = { path = "../qy-strings" }
"""
        m = parse_manifest(toml)
        assert m.pkg_path == "github.com/user/qy-json"
        assert m.version == "0.3.1"
        assert m.description == "JSON parser"
        assert m.license == "MIT"
        assert m.authors == ("Alice <a@b.com>",)
        assert m.entry == "src/main.qy"
        assert m.src == "lib"
        assert m.export_modules == ("json", "json.parse")
        assert len(m.dependencies) == 2
        assert m.dependencies[0].path == "github.com/user/qy-strings"
        assert m.dependencies[0].min_version == "0.2.0"
        assert len(m.dev_dependencies) == 1
        assert len(m.replaces) == 1
        assert m.replaces[0].local_path == "../qy-strings"

    def test_is_executable(self):
        from qy.project.manifest import parse_manifest

        no_entry = parse_manifest('[package]\npath = "x"\nversion = "0.1.0"\n')
        assert not no_entry.is_executable

        with_entry = parse_manifest(
            '[package]\npath = "x"\nversion = "0.1.0"\nentry = "src/main.qy"\n'
        )
        assert with_entry.is_executable

    def test_serialize_roundtrip(self):
        from qy.project.manifest import parse_manifest
        from qy.project.manifest import serialize_manifest

        toml = """\
[package]
path = "github.com/user/hello"
version = "1.0.0"
description = "test"

[dependencies]
"github.com/dep/a" = "0.1.0"
"""
        m = parse_manifest(toml)
        serialized = serialize_manifest(m)
        m2 = parse_manifest(serialized)
        assert m2.pkg_path == m.pkg_path
        assert m2.version == m.version
        assert m2.description == m.description
        assert m2.dependencies == m.dependencies

    def test_parse_manifest_file(self, tmp_path: Path):
        from qy.project.manifest import parse_manifest_file

        f = tmp_path / "qy.toml"
        f.write_text('[package]\npath = "test/pkg"\nversion = "2.0.0"\n', encoding="utf-8")
        m = parse_manifest_file(f)
        assert m.pkg_path == "test/pkg"
        assert m.version == "2.0.0"


# ─── Package ────────────────────────────────────────────────────────────────


class TestPackage:
    def test_is_package_path(self):
        from qy.project.package import is_package_path

        assert is_package_path("github.com/user/repo")
        assert is_package_path("gitlab.com/org/lib/sub")
        assert not is_package_path("qy.core")
        assert not is_package_path("hello")
        assert not is_package_path("./local.qy")

    def test_split_package_module(self):
        from qy.project.package import split_package_module

        known = {"github.com/user/qy-json", "github.com/user/qy-io"}
        pkg, sub = split_package_module("github.com/user/qy-json/parse", known)
        assert pkg == "github.com/user/qy-json"
        assert sub == "parse"

        pkg, sub = split_package_module("github.com/user/qy-json", known)
        assert pkg == "github.com/user/qy-json"
        assert sub == ""

    def test_split_package_module_unknown(self):
        from qy.project.package import split_package_module

        pkg, sub = split_package_module("github.com/unknown/pkg/mod", set())
        assert pkg == "github.com/unknown/pkg/mod"
        assert sub == ""

    def test_package_id(self):
        from qy.project.package import PackageId

        pid = PackageId(path="github.com/user/lib", version="1.2.3")
        assert str(pid) == "github.com/user/lib@v1.2.3"
        assert pid.domain == "github.com"
        assert pid.repo_path == "github.com/user/lib"

    def test_load_package(self, tmp_path: Path):
        from qy.project.package import load_package

        (tmp_path / "qy.toml").write_text(
            '[package]\npath = "github.com/test/pkg"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.qy").write_text("; root", encoding="utf-8")
        (src / "util.qy").write_text("; util", encoding="utf-8")

        pkg = load_package(tmp_path)
        assert pkg.id.path == "github.com/test/pkg"
        assert pkg.src_dir == src
        assert pkg.root_module_path == src / "mod.qy"
        assert pkg.resolve_submodule("util") == src / "util.qy"
        assert pkg.resolve_submodule("nonexist") is None

    def test_package_exports_visibility(self, tmp_path: Path):
        from qy.project.manifest import Manifest
        from qy.project.package import Package
        from qy.project.package import PackageId

        manifest = Manifest(
            pkg_path="test/pkg",
            version="0.1.0",
            export_modules=("api", "api/v2"),
        )
        pkg = Package(id=PackageId("test/pkg", "0.1.0"), root=tmp_path, manifest=manifest)

        assert pkg.is_exported("api")
        assert pkg.is_exported("api/v2")
        assert not pkg.is_exported("secret")
        assert not pkg.is_exported("internal/helper")

    def test_internal_always_hidden(self, tmp_path: Path):
        from qy.project.manifest import Manifest
        from qy.project.package import Package
        from qy.project.package import PackageId

        manifest = Manifest(pkg_path="test/pkg", version="0.1.0", export_modules=None)
        pkg = Package(id=PackageId("test/pkg", "0.1.0"), root=tmp_path, manifest=manifest)

        assert pkg.is_exported("anything")
        assert not pkg.is_exported("internal/secret")
        assert not pkg.is_exported("foo/internal/bar")


# ─── MVS Resolver ───────────────────────────────────────────────────────────


class TestMVSResolver:
    def test_single_dependency(self):
        from qy.project.manifest import Dependency
        from qy.project.manifest import Manifest
        from qy.project.resolve import LocalManifestProvider
        from qy.project.resolve import resolve

        root = Manifest(
            pkg_path="root",
            version="1.0.0",
            dependencies=(Dependency("dep/a", "1.0.0"),),
        )
        provider = LocalManifestProvider()
        provider.register(Manifest(pkg_path="dep/a", version="1.0.0"))

        bl = resolve(root, provider)
        dep_a = bl.get("dep/a")
        assert dep_a is not None
        assert dep_a.version == "1.0.0"

    def test_mvs_selects_maximum_minimum(self):
        from qy.project.manifest import Dependency
        from qy.project.manifest import Manifest
        from qy.project.resolve import LocalManifestProvider
        from qy.project.resolve import resolve

        root = Manifest(
            pkg_path="root",
            version="1.0.0",
            dependencies=(
                Dependency("dep/a", "1.0.0"),
                Dependency("dep/b", "1.0.0"),
            ),
        )
        dep_a = Manifest(
            pkg_path="dep/a",
            version="1.0.0",
            dependencies=(Dependency("dep/shared", "1.2.0"),),
        )
        dep_b = Manifest(
            pkg_path="dep/b",
            version="1.0.0",
            dependencies=(Dependency("dep/shared", "1.5.0"),),
        )
        shared = Manifest(pkg_path="dep/shared", version="1.5.0")

        provider = LocalManifestProvider()
        provider.register(dep_a)
        provider.register(dep_b)
        provider.register(shared)

        bl = resolve(root, provider)
        shared = bl.get("dep/shared")
        assert shared is not None
        assert shared.version == "1.5.0"

    def test_transitive_dependencies(self):
        from qy.project.manifest import Dependency
        from qy.project.manifest import Manifest
        from qy.project.resolve import LocalManifestProvider
        from qy.project.resolve import resolve

        root = Manifest(
            pkg_path="root",
            version="1.0.0",
            dependencies=(Dependency("dep/a", "1.0.0"),),
        )
        dep_a = Manifest(
            pkg_path="dep/a",
            version="1.0.0",
            dependencies=(Dependency("dep/b", "2.0.0"),),
        )
        dep_b = Manifest(
            pkg_path="dep/b",
            version="2.0.0",
            dependencies=(Dependency("dep/c", "0.1.0"),),
        )
        dep_c = Manifest(pkg_path="dep/c", version="0.1.0")

        provider = LocalManifestProvider()
        provider.register(dep_a)
        provider.register(dep_b)
        provider.register(dep_c)

        bl = resolve(root, provider)
        dep_a = bl.get("dep/a")
        dep_b = bl.get("dep/b")
        dep_c = bl.get("dep/c")
        assert dep_a is not None
        assert dep_b is not None
        assert dep_c is not None
        assert dep_a.version == "1.0.0"
        assert dep_b.version == "2.0.0"
        assert dep_c.version == "0.1.0"

    def test_no_dependencies(self):
        from qy.project.manifest import Manifest
        from qy.project.resolve import LocalManifestProvider
        from qy.project.resolve import resolve

        root = Manifest(pkg_path="root", version="1.0.0")
        bl = resolve(root, LocalManifestProvider())
        assert bl.modules == ()

    def test_diamond_dependency(self):
        from qy.project.manifest import Dependency
        from qy.project.manifest import Manifest
        from qy.project.resolve import LocalManifestProvider
        from qy.project.resolve import resolve

        #     root
        #    /    \
        #   a      b
        #    \    /
        #     shared
        root = Manifest(
            pkg_path="root",
            version="1.0.0",
            dependencies=(
                Dependency("dep/a", "1.0.0"),
                Dependency("dep/b", "1.0.0"),
            ),
        )
        dep_a = Manifest(
            pkg_path="dep/a",
            version="1.0.0",
            dependencies=(Dependency("dep/shared", "1.0.0"),),
        )
        dep_b = Manifest(
            pkg_path="dep/b",
            version="1.0.0",
            dependencies=(Dependency("dep/shared", "2.0.0"),),
        )
        shared_v2 = Manifest(pkg_path="dep/shared", version="2.0.0")

        provider = LocalManifestProvider()
        provider.register(dep_a)
        provider.register(dep_b)
        provider.register(shared_v2)

        bl = resolve(root, provider)
        shared = bl.get("dep/shared")
        assert shared is not None
        assert shared.version == "2.0.0"

    def test_build_list_as_dict(self):
        from qy.project.manifest import Dependency
        from qy.project.manifest import Manifest
        from qy.project.resolve import LocalManifestProvider
        from qy.project.resolve import resolve

        root = Manifest(
            pkg_path="root",
            version="1.0.0",
            dependencies=(
                Dependency("dep/a", "1.0.0"),
                Dependency("dep/b", "2.3.0"),
            ),
        )
        provider = LocalManifestProvider()
        provider.register(Manifest(pkg_path="dep/a", version="1.0.0"))
        provider.register(Manifest(pkg_path="dep/b", version="2.3.0"))

        bl = resolve(root, provider)
        d = bl.as_dict()
        assert d == {"dep/a": "1.0.0", "dep/b": "2.3.0"}


class TestVersionCompare:
    def test_compare(self):
        from qy.project.resolve import compare_versions
        from qy.project.resolve import max_version

        assert compare_versions("1.0.0", "1.0.0") == 0
        assert compare_versions("1.0.0", "2.0.0") == -1
        assert compare_versions("2.0.0", "1.0.0") == 1
        assert compare_versions("1.2.3", "1.2.4") == -1
        assert compare_versions("1.10.0", "1.9.0") == 1

        assert max_version("1.0.0", "2.0.0") == "2.0.0"
        assert max_version("3.0.0", "2.0.0") == "3.0.0"


# ─── Checksum ───────────────────────────────────────────────────────────────


class TestChecksum:
    def test_parse_sum_file(self):
        from qy.project.checksum import parse_sum_file

        content = """\
github.com/user/lib v1.0.0 h1:abc123
github.com/user/lib v1.0.0/src h1:def456
"""
        cf = parse_sum_file(content)
        assert len(cf.entries) == 2
        assert cf.lookup("github.com/user/lib", "1.0.0", "") == "abc123"
        assert cf.lookup("github.com/user/lib", "1.0.0", "src") == "def456"

    def test_add_and_remove(self):
        from qy.project.checksum import ChecksumFile

        cf = ChecksumFile(entries=[])
        cf.add("pkg/a", "1.0.0", "src", "hash1")
        assert cf.lookup("pkg/a", "1.0.0", "src") == "hash1"

        cf.add("pkg/a", "1.0.0", "src", "hash2")
        assert cf.lookup("pkg/a", "1.0.0", "src") == "hash2"

        cf.remove("pkg/a")
        assert cf.lookup("pkg/a", "1.0.0", "src") is None

    def test_save_and_load(self, tmp_path: Path):
        from qy.project.checksum import ChecksumFile
        from qy.project.checksum import load_sum_file
        from qy.project.checksum import save_sum_file

        cf = ChecksumFile(entries=[])
        cf.add("github.com/user/lib", "1.0.0", "", "abc")
        cf.add("github.com/user/lib", "1.0.0", "src", "def")

        path = tmp_path / "qy.sum"
        save_sum_file(path, cf)

        loaded = load_sum_file(path)
        assert loaded.lookup("github.com/user/lib", "1.0.0", "") == "abc"
        assert loaded.lookup("github.com/user/lib", "1.0.0", "src") == "def"

    def test_hash_directory(self, tmp_path: Path):
        from qy.project.checksum import hash_directory

        (tmp_path / "a.qy").write_text("hello", encoding="utf-8")
        (tmp_path / "b.qy").write_text("world", encoding="utf-8")

        h1 = hash_directory(tmp_path)
        assert len(h1) == 64  # sha256 hex

        (tmp_path / "a.qy").write_text("changed", encoding="utf-8")
        h2 = hash_directory(tmp_path)
        assert h1 != h2


# ─── Fetch / Cache ──────────────────────────────────────────────────────────


class TestFetchCache:
    def test_cache_operations(self, tmp_path: Path, monkeypatch):
        from qy.project import fetch

        monkeypatch.setenv("QY_HOME", str(tmp_path))

        assert not fetch.is_cached("github.com/user/lib", "1.0.0")
        assert fetch.get_cached("github.com/user/lib", "1.0.0") is None

        # create a fake cached package
        d = fetch.cached_package_dir("github.com/user/lib", "1.0.0")
        d.mkdir(parents=True)
        (d / "qy.toml").write_text(
            '[package]\npath = "github.com/user/lib"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        assert fetch.is_cached("github.com/user/lib", "1.0.0")
        cached = fetch.get_cached("github.com/user/lib", "1.0.0")
        assert cached is not None
        assert cached.path == "github.com/user/lib"
        assert cached.version == "1.0.0"

    def test_cache_from_local(self, tmp_path: Path):
        from qy.project.fetch import cache_from_local

        cached = cache_from_local("github.com/test/pkg", "0.1.0", tmp_path)
        assert cached.root == tmp_path

    def test_clear_cache(self, tmp_path: Path, monkeypatch):
        from qy.project import fetch

        monkeypatch.setenv("QY_HOME", str(tmp_path))

        d = fetch.cached_package_dir("github.com/a/b", "1.0.0")
        d.mkdir(parents=True)
        (d / "qy.toml").write_text("x", encoding="utf-8")

        assert fetch.is_cached("github.com/a/b", "1.0.0")
        fetch.clear_cache("github.com/a/b", "1.0.0")
        assert not fetch.is_cached("github.com/a/b", "1.0.0")


# ─── CLI pkg commands ───────────────────────────────────────────────────────


class TestPkgCLI:
    def test_pkg_init(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner

        from qy.cli import create_app
        from qy.project.manifest import parse_manifest_file

        runner = CliRunner()
        app = create_app()
        result = runner.invoke(app, ["pkg", "init", "github.com/test/mypkg"])
        assert result.exit_code == 0
        assert (tmp_path / "qy.toml").exists()
        assert (tmp_path / "src" / "mod.qy").exists()

        m = parse_manifest_file(tmp_path / "qy.toml")
        assert m.pkg_path == "github.com/test/mypkg"
        assert m.version == "0.1.0"

    def test_pkg_add_and_remove(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner

        from qy.cli import create_app
        from qy.project.manifest import parse_manifest_file

        runner = CliRunner()
        app = create_app()

        runner.invoke(app, ["pkg", "init", "github.com/test/proj"])

        result = runner.invoke(app, ["pkg", "add", "github.com/dep/lib", "--version", "1.2.0"])
        assert result.exit_code == 0

        m = parse_manifest_file(tmp_path / "qy.toml")
        assert len(m.dependencies) == 1
        assert m.dependencies[0].path == "github.com/dep/lib"
        assert m.dependencies[0].min_version == "1.2.0"

        result = runner.invoke(app, ["pkg", "remove", "github.com/dep/lib"])
        assert result.exit_code == 0

        m = parse_manifest_file(tmp_path / "qy.toml")
        assert len(m.dependencies) == 0

    def test_pkg_graph(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner

        from qy.cli import create_app

        runner = CliRunner()
        app = create_app()

        runner.invoke(app, ["pkg", "init", "github.com/test/proj"])
        runner.invoke(app, ["pkg", "add", "github.com/dep/a", "--version", "1.0.0"])

        result = runner.invoke(app, ["pkg", "graph"])
        assert result.exit_code == 0
        assert "github.com/test/proj@v0.1.0" in result.output
        assert "github.com/dep/a@v1.0.0" in result.output


# ─── Integration: package path in import system ─────────────────────────────


class TestPackageImportIntegration:
    def test_package_path_resolution_with_replace(self, tmp_path: Path, monkeypatch):
        """Test that a package with [replace] can be resolved via the import system."""
        monkeypatch.chdir(tmp_path)

        # Create the dependency package
        dep_dir = tmp_path / "dep-pkg"
        dep_dir.mkdir()
        (dep_dir / "qy.toml").write_text(
            '[package]\npath = "github.com/test/dep"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        dep_src = dep_dir / "src"
        dep_src.mkdir()
        (dep_src / "mod.qy").write_text(
            "(module github.com/test/dep\n  (define answer 42)\n  (exports answer))\n",
            encoding="utf-8",
        )

        # Create the main project
        (tmp_path / "qy.toml").write_text(
            """\
[package]
path = "github.com/test/main"
version = "0.1.0"

[dependencies]
"github.com/test/dep" = "0.1.0"

[replace]
"github.com/test/dep" = { path = "./dep-pkg" }
""",
            encoding="utf-8",
        )

        from qy.project.package import is_package_path
        from qy.project.package import load_package
        from qy.project.package import split_package_module

        assert is_package_path("github.com/test/dep")

        known = {"github.com/test/dep"}
        pkg_path, sub = split_package_module("github.com/test/dep", known)
        assert pkg_path == "github.com/test/dep"
        assert sub == ""

        pkg = load_package(dep_dir)
        assert pkg.root_module_path.exists()
