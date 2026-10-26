#!/usr/bin/env python3
"""Build a reproducible manifest for locally obtainable source archives.

The Mooncakes registry's old full scan retained hashes and protocol signals but
not every ZIP body.  This helper inventories the ZIP bodies that are actually
present in the workspace, adds public contest candidates when requested, and
records a SHA-256 for every archive.  It never downloads or executes source.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
from typing import Iterable


ARCHIVE_RE = re.compile(r"^(?P<owner>.+?)__(?P<package>.+?)@(?P<version>.+?)--(?P<digest>[0-9a-f]+)\.zip$", re.I)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_entry(path: pathlib.Path, root: pathlib.Path) -> dict:
    match = ARCHIVE_RE.match(path.name)
    if match:
        owner = match.group("owner")
        package = match.group("package")
        version = match.group("version")
        name = f"{owner}/{package}@{version}"
        url = f"https://download.mooncakes.io/user/{owner}/{package}/{version}.zip"
        encoded = match.group("digest")
    else:
        name = path.stem
        url = ""
        encoded = ""
    return {
        "name": name,
        "kind": "mooncakes_cached_archive",
        "path": str(path.resolve()),
        "source_url": url,
        "archive_sha256": sha256(path),
        "filename_digest_hint": encoded,
        "archive_root": str(root.resolve()),
        "permission": "locally cached public release ZIP; static read only",
    }


def iter_archives(roots: Iterable[pathlib.Path]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        root = root.resolve()
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(root.rglob("*.zip"))
        for path in paths:
            if not path.is_file():
                continue
            identity = str(path.resolve())
            if identity in seen:
                continue
            seen.add(identity)
            result.append(archive_entry(path, root))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", action="append", default=[], help="directory or ZIP; repeatable")
    parser.add_argument("--contest-manifest", help="existing contest manifest whose projects are appended")
    parser.add_argument("--out", required=True, help="manifest output JSON path")
    args = parser.parse_args()
    entries = iter_archives(pathlib.Path(value) for value in args.archive_root)
    contest_meta: dict = {}
    if args.contest_manifest:
        contest_path = pathlib.Path(args.contest_manifest).resolve()
        contest_meta = json.loads(contest_path.read_text(encoding="utf-8"))
        for item in contest_meta.get("projects", []):
            if isinstance(item, dict):
                entry = dict(item)
                entry.setdefault("kind", "public_contest_candidate")
                entries.append(entry)
    # Keep a stable order and avoid a duplicate path if an archive was also
    # listed by a contest manifest.
    deduped: list[dict] = []
    seen_paths: set[str] = set()
    for item in sorted(entries, key=lambda value: (str(value.get("name", "")), str(value.get("path", "")))):
        path = str(pathlib.Path(str(item.get("path", ""))).resolve()) if item.get("path") else ""
        if path and path in seen_paths:
            continue
        if path:
            seen_paths.add(path)
        deduped.append(item)
    payload = {
        "schema": "moon-jmap-source-comparison-manifest/v1",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "contest": contest_meta.get("contest", "Mooncakes public cached source and public contest candidates"),
        "snapshot_date": dt.date.today().isoformat(),
        "expected_count": contest_meta.get("expected_count"),
        "official_roster_verified": bool(contest_meta.get("official_roster_verified", False)),
        "scope_note": "Only locally obtainable ZIP bodies and explicitly listed public candidates are included; this is not an official contest roster.",
        "projects": deduped,
    }
    out = pathlib.Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "projects": len(deduped), "archives": len(entries) - len(contest_meta.get("projects", [])), "contest_candidates": len(contest_meta.get("projects", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
