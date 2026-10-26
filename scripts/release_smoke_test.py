#!/usr/bin/env python3
"""Verify and smoke-test a MoonJMAP source archive in a fresh directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


REQUIRED = {
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "moon.mod",
    "moon.pkg",
    "RELEASE-MANIFEST.json",
    "src/jmap/__init__.py",
    "src/jmap/methods.py",
    "src/sync/sync.mbt",
    "src/email/email.mbt",
    "cmd/differential/main.mbt",
    "cmd/differential/moon.pkg",
    "cmd/demo/main.mbt",
    ".github/workflows/ci.yml",
    "docs/source-provenance.md",
    "tests/test_jmap_wire.py",
    "tests/vectors/incremental_cases.json",
    "scripts/build_source_archive.py",
    "scripts/run_differential.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member(name: str) -> None:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise RuntimeError(f"archive path escapes root: {name}")


def extract(archive: Path, destination: Path) -> Path:
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as source:
            members = source.getmembers()
            roots = set()
            for member in members:
                safe_member(member.name)
                if not member.isfile():
                    raise RuntimeError(f"non-regular archive member: {member.name}")
                roots.add(PurePosixPath(member.name).parts[0])
            if len(roots) != 1:
                raise RuntimeError(f"archive must have one package root, found {sorted(roots)}")
            source.extractall(destination)
    elif archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as source:
            roots = set()
            for member in source.infolist():
                safe_member(member.filename)
                if member.is_dir():
                    continue
                mode = (member.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise RuntimeError(f"symbolic links are not allowed: {member.filename}")
                roots.add(PurePosixPath(member.filename).parts[0])
            if len(roots) != 1:
                raise RuntimeError(f"archive must have one package root, found {sorted(roots)}")
            source.extractall(destination)
    else:
        raise RuntimeError("archive must end in .tar.gz or .zip")
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"expected exactly one package root, found {roots}")
    return roots[0]


def verify_manifest(root: Path) -> dict:
    manifest_path = root / "RELEASE-MANIFEST.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("artifact") != "local-source":
        raise RuntimeError("unexpected archive artifact type")
    entries = data.get("files", [])
    listed = set()
    for entry in entries:
        relative = entry["path"]
        safe_member(relative)
        if relative in listed or relative == "RELEASE-MANIFEST.json":
            raise RuntimeError(f"duplicate or reserved manifest path: {relative}")
        listed.add(relative)
        path = root / entry["path"]
        if not path.is_file():
            raise RuntimeError(f"manifest file missing: {entry['path']}")
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise RuntimeError(f"manifest digest mismatch: {entry['path']}")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "RELEASE-MANIFEST.json"
    }
    if actual != listed:
        raise RuntimeError(f"manifest file set mismatch: extra={sorted(actual - listed)}, missing={sorted(listed - actual)}")
    return data


def run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> None:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    completed = subprocess.run(command, cwd=cwd, env=merged, text=True, capture_output=True)
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")


def smoke(root: Path) -> None:
    available = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    missing = sorted(REQUIRED - available)
    if missing:
        raise RuntimeError(f"required archive files missing: {missing}")
    verify_manifest(root)
    run([sys.executable, "-c", "from jmap import EmailQueryRequest, encode_request; print(EmailQueryRequest)"], root, env={"PYTHONPATH": "src"})
    # Run every packaged Python regression test. The metrics harness writes
    # only under its caller-provided temporary output directory, so this also
    # checks that the archive remains self-contained after extraction.
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], root, env={"PYTHONPATH": "src"})
    run([sys.executable, "tests/verify.py", "--strict-structure"], root)
    run([sys.executable, "examples/replay_vectors.py"], root)
    run([sys.executable, "examples/codec_roundtrip.py"], root)
    run([sys.executable, "scripts/run_differential.py"], root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="moonjmap-release-") as directory:
        root = extract(args.archive.resolve(), Path(directory))
        metadata = smoke(root)
        print(f"PASS archive={args.archive} package={root.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
