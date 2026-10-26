#!/usr/bin/env python3
"""Build deterministic local MoonJMAP source archives.

The output is deliberately a source artifact, not a registry upload.  An
explicit allowlist prevents `_build/`, exploratory `work/`, local reports and
machine-specific files from leaking into a release package.  Tar and ZIP
members use stable ordering and timestamps so rebuilding from the same source
tree produces byte-identical archives.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^version\s*=\s*\"([^\"]+)\"\s*$", re.MULTILINE)
PACKAGE_RE = re.compile(r"^name\s*=\s*\"([^\"]+)\"\s*$", re.MULTILINE)

# Source-delivery allowlist. Keep generated build products and the large
# investigative work/outputs directories out of a package intended for users.
TOP_LEVEL_FILES = (
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "moon.mod",
    "moon.pkg",
    "pkg.generated.mbti",
)
TOP_LEVEL_DIRS = ("cmd", "docs", "examples", "python", "scripts", "src", "tests")
OPTIONAL_TOP_LEVEL_FILES = (".moonignore",)


def project_metadata(root: Path) -> tuple[str, str]:
    text = (root / "moon.mod").read_text(encoding="utf-8")
    version_match = VERSION_RE.search(text)
    package_match = PACKAGE_RE.search(text)
    if not version_match or not package_match:
        raise SystemExit("moon.mod must contain name and version")
    return package_match.group(1), version_match.group(1)


def iter_files(root: Path, *, excluded_root: Path | None = None) -> list[Path]:
    files: list[Path] = []
    for name in TOP_LEVEL_FILES:
        path = root / name
        if not path.is_file():
            raise SystemExit(f"required source file is missing: {path}")
        files.append(path)
    for name in OPTIONAL_TOP_LEVEL_FILES:
        path = root / name
        if path.is_file():
            files.append(path)
    for directory in TOP_LEVEL_DIRS:
        base = root / directory
        if not base.is_dir():
            raise SystemExit(f"required source directory is missing: {base}")
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if excluded_root is not None:
                try:
                    path.relative_to(excluded_root)
                except ValueError:
                    pass
                else:
                    continue
            if any(part in {"__pycache__", ".pytest_cache"} for part in relative.parts):
                continue
            if path.name.endswith((".pyc", ".pyo")) or path.name == ".DS_Store":
                continue
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def manifest(root: Path, files: Iterable[Path], package_root: str, package: str, version: str) -> dict:
    entries = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        entries.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)})
    return {
        "format": 1,
        "artifact": "local-source",
        "package": package,
        "version": version,
        "root": package_root,
        "files": entries,
    }


def manifest_bytes(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def tar_bytes(root: Path, files: list[Path], package_root: str, manifest_data: dict) -> bytes:
    payload = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    with tarfile.open(fileobj=payload, mode="w") as archive:
        all_members = [(path.relative_to(root).as_posix(), path.read_bytes()) for path in files]
        all_members.append(("RELEASE-MANIFEST.json", manifest_bytes(manifest_data)))
        for relative, content in sorted(all_members):
            info = tarfile.TarInfo(f"{package_root}/{relative}")
            info.size = len(content)
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(content))
    payload.seek(0)
    raw = payload.read()
    return gzip.compress(raw, compresslevel=9, mtime=0)


def zip_bytes(root: Path, files: list[Path], package_root: str, manifest_data: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        all_members = [(path.relative_to(root).as_posix(), path.read_bytes()) for path in files]
        all_members.append(("RELEASE-MANIFEST.json", manifest_bytes(manifest_data)))
        for relative, content in sorted(all_members):
            info = zipfile.ZipInfo(f"{package_root}/{relative}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, content)
    return output.getvalue()


def write_outputs(root: Path, output_dir: Path) -> dict:
    package, version = project_metadata(root)
    package_root = f"moonjmap-{version}"
    output_dir = output_dir.resolve()
    files = iter_files(root, excluded_root=output_dir)
    data = manifest(root, files, package_root, package, version)
    output_dir.mkdir(parents=True, exist_ok=True)
    tar_path = output_dir / f"{package_root}-src.tar.gz"
    zip_path = output_dir / f"{package_root}-src.zip"
    manifest_path = output_dir / f"{package_root}-manifest.json"
    for path in (tar_path, zip_path, manifest_path):
        path.unlink(missing_ok=True)
    tar_path.write_bytes(tar_bytes(root, files, package_root, data))
    zip_path.write_bytes(zip_bytes(root, files, package_root, data))
    result = {
        **data,
        "archives": {
            "tar.gz": {"path": tar_path.name, "bytes": tar_path.stat().st_size, "sha256": digest(tar_path)},
            "zip": {"path": zip_path.name, "bytes": zip_path.stat().st_size, "sha256": digest(zip_path)},
        },
    }
    manifest_path.write_bytes(manifest_bytes(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    result = write_outputs(ROOT, output_dir)
    print(json.dumps({"output_dir": str(output_dir), **result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
