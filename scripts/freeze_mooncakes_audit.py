#!/usr/bin/env python3
"""Freeze the live Mooncakes registry and audit the current MoonJMAP sources.

The registry is a moving catalog.  This command captures the raw module list,
downloads the published ZIP for every current ``(name, version)`` coordinate,
checks the official manifest checksum and ZIP CRC, records readable source
statistics and nested archives that remain unopened, then compares the three
current MoonJMAP production files with every readable published package.

The audit is static evidence.  It does not execute third-party packages and
does not turn lexical similarity, public-catalog coverage or a zero exact hash
hit into an originality or contest-eligibility claim.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULES_URL = "https://mooncakes.io/api/v0/modules/"
DOWNLOAD_BASE = "https://download.mooncakes.io/user/"
MANIFEST_BASE = "https://mooncakes.io/api/v0/manifest/"
CODE_SUFFIXES = {
    ".mbt", ".mbti", ".rs", ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    ".go", ".c", ".h", ".cpp", ".hpp", ".java", ".kt", ".swift", ".lua",
    ".zig", ".sh", ".sql", ".json", ".toml", ".yaml", ".yml", ".xml",
}
TEXT_SUFFIXES = CODE_SUFFIXES | {".md", ".rst", ".txt", ".cfg", ".ini", ".lock"}
NESTED_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
TARGET_FILES = [
    "src/email/email.mbt",
    "src/jmap/api.mbt",
    "src/sync/sync.mbt",
]
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|==|!=|<=|>=|=>|::|[{}()\[\],.:;=+*/<>?-]")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def current_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def fetch(url: str, timeout: float = 120.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MoonJMAP-0.2.0-audit/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def archive_name(module: dict[str, Any]) -> str:
    safe = str(module["name"]).replace("/", "__")
    return f"{safe}@{module['version']}--{sha256(str(module['name']).encode())[:12]}.zip"


def download_one(module: dict[str, Any], archive_dir: pathlib.Path) -> dict[str, Any]:
    name = str(module["name"])
    version = str(module["version"])
    output = archive_dir / archive_name(module)
    url = DOWNLOAD_BASE + urllib.parse.quote(name, safe="/") + "/" + urllib.parse.quote(version) + ".zip"
    error: str | None = None
    for attempt in range(4):
        try:
            if output.exists() and output.stat().st_size > 0:
                data = output.read_bytes()
            else:
                data = fetch(url)
                if not data.startswith(b"PK"):
                    raise ValueError("download is not a ZIP archive")
                output.write_bytes(data)
            return {
                "name": name,
                "version": version,
                "archive": str(output),
                "archive_sha256": sha256(data),
                "archive_bytes": len(data),
                "download_status": "ok",
                "attempt": attempt + 1,
                "url": url,
            }
        except Exception as exc:  # retain the failure as evidence
            error = repr(exc)
            time.sleep(1 + attempt)
    return {"name": name, "version": version, "download_status": "error", "error": error, "url": url}


def manifest_one(module: dict[str, Any], archive_map: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    name = str(module["name"])
    version = str(module["version"])
    url = MANIFEST_BASE + urllib.parse.quote(name, safe="/") + "@" + urllib.parse.quote(version)
    result = {"name": name, "version": version, "url": url}
    try:
        # Keep registry refresh bounded.  A single unavailable manifest must
        # be recorded as an evidence gap instead of holding the full freeze.
        value = json.loads(fetch(url, 15).decode("utf-8"))
        metadata = value.get("metadata") if isinstance(value, dict) else {}
        official = metadata.get("checksum") if isinstance(metadata, dict) else None
        result["official_checksum"] = official
        local = archive_map.get((name, version), {}).get("archive_sha256")
        result["archive_sha256"] = local
        result["checksum_match"] = bool(official and local and official == local)
        result["manifest_status"] = "ok"
    except Exception as exc:
        result["manifest_status"] = "error"
        result["error"] = repr(exc)
    return result


def normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def tokens(text: str, shape: bool = False) -> list[str]:
    values = TOKEN_RE.findall(text)
    if not shape:
        return values
    return [
        "ID" if IDENT_RE.fullmatch(value) else "NUM" if value[:1].isdigit() else value
        for value in values
    ]


def shingles(values: list[str], width: int = 20) -> set[str]:
    return {
        "\x1f".join(values[index : index + width])
        for index in range(max(0, len(values) - width + 1))
    }


def target_signals(root: pathlib.Path) -> tuple[dict[str, Any], dict[str, set[str]]]:
    files: list[dict[str, Any]] = []
    exact: set[str] = set()
    lines: set[str] = set()
    exact_tokens: set[str] = set()
    shape_tokens: set[str] = set()
    for relative in TARGET_FILES:
        path = root / relative
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        files.append({"path": relative, "bytes": len(raw), "sha256": sha256(raw)})
        exact.add(sha256(raw))
        lines.update(normalize_line(line) for line in text.splitlines() if normalize_line(line))
        exact_tokens.update(shingles(tokens(text)))
        shape_tokens.update(shingles(tokens(text, shape=True)))
    aggregate = hashlib.sha256()
    for item in files:
        aggregate.update(item["path"].encode())
        aggregate.update(item["sha256"].encode())
    return (
        {
            "files": files,
            "tree_sha256": aggregate.hexdigest(),
            "bytes": sum(item["bytes"] for item in files),
        },
        {"exact": exact, "lines": lines, "exact_tokens": exact_tokens, "shape_tokens": shape_tokens},
    )


def scan_archive(item: dict[str, Any], target: dict[str, set[str]]) -> dict[str, Any]:
    if item.get("download_status") != "ok":
        return {**item, "source_status": "unavailable"}
    path = pathlib.Path(str(item["archive"]))
    result = {**item}
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            source_files = 0
            source_bytes = 0
            text_files = 0
            nested: list[dict[str, Any]] = []
            matched_lines: set[str] = set()
            matched_exact_tokens: set[str] = set()
            matched_shape_tokens: set[str] = set()
            exact_hits: list[str] = []
            for member in archive.infolist():
                if member.is_dir():
                    continue
                suffix = pathlib.PurePosixPath(member.filename).suffix.lower()
                if suffix in NESTED_SUFFIXES:
                    nested.append({"path": member.filename, "bytes": member.file_size, "reason": "nested-container-not-expanded"})
                if suffix not in CODE_SUFFIXES and suffix not in TEXT_SUFFIXES:
                    continue
                raw = archive.read(member)
                if b"\0" in raw[:4096]:
                    continue
                text = raw.decode("utf-8", "replace")
                source_files += 1
                source_bytes += len(raw)
                text_files += 1
                for line in text.splitlines():
                    normalized = normalize_line(line)
                    if normalized and normalized in target["lines"]:
                        matched_lines.add(normalized)
                for shingle in shingles(tokens(text)):
                    if shingle in target["exact_tokens"]:
                        matched_exact_tokens.add(shingle)
                for shingle in shingles(tokens(text, shape=True)):
                    if shingle in target["shape_tokens"]:
                        matched_shape_tokens.add(shingle)
                file_hash = sha256(raw)
                if file_hash in target["exact"]:
                    exact_hits.append(member.filename)
            line_intersection = len(matched_lines)
            exact_intersection = len(matched_exact_tokens)
            shape_intersection = len(matched_shape_tokens)
            result.update(
                {
                    "source_status": "ok" if bad is None else "crc-error",
                    "zip_members": len(archive.infolist()),
                    "zip_bad_member": bad,
                    "source_files": source_files,
                    "source_bytes": source_bytes,
                    "text_files": text_files,
                    "nested_containers_not_expanded": nested,
                    "nested_container_count": len(nested),
                    "exact_file_hits": exact_hits,
                    "exact_token_intersection": exact_intersection,
                    "exact_token_containment": exact_intersection / max(1, len(target["exact_tokens"])),
                    "shape_token_intersection": shape_intersection,
                    "shape_token_containment": shape_intersection / max(1, len(target["shape_tokens"])),
                    "canonical_line_intersection": line_intersection,
                    "canonical_line_containment": line_intersection / max(1, len(target["lines"])),
                }
            )
    except (zipfile.BadZipFile, OSError, UnicodeError) as exc:
        result.update({"source_status": "error", "source_error": repr(exc)})
    return result


def write_report(out_dir: pathlib.Path, report: dict[str, Any], records: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "snapshot.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "source-audit.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8"
    )
    top = sorted(records, key=lambda item: (item.get("shape_token_containment", 0), item.get("canonical_line_containment", 0)), reverse=True)[:30]
    md = [
        "# MoonJMAP 0.2.0 Mooncakes.io 当前目录冻结与源码审计",
        "",
        f"- 捕获时间（UTC）：`{report['captured_at']}`",
        f"- 被审计仓库提交：`{report['repository_commit'] or 'unknown'}`",
        f"- 目录原始 JSON：`{report['catalog']['raw_path']}`",
        f"- 目录 SHA-256：`{report['catalog']['raw_sha256']}`",
        f"- 当前发布坐标：`{report['catalog']['module_count']}` 个 `(name, version)`",
        f"- ZIP 下载成功：`{report['artifacts']['download_ok']}`；失败：`{report['artifacts']['download_errors']}`",
        f"- manifest checksum 抽样刷新一致：`{report['artifacts']['manifest_matches']}`；不一致：`{report['artifacts']['manifest_mismatches']}`；读取错误：`{report['artifacts']['manifest_errors']}`；未请求：`{report['artifacts']['manifest_not_requested']}`（其余坐标以下载 ZIP SHA-256 记录）",
        f"- ZIP CRC 可读源码：`{report['artifacts']['source_ok']}`；未展开嵌套容器：`{report['artifacts']['nested_container_total']}` 个；源码字节：`{report['artifacts']['source_bytes']}`",
        f"- MoonJMAP 生产源码树 SHA-256：`{report['target']['tree_sha256']}`（`{report['target']['bytes']}` bytes，3 个文件）",
        "",
        "> 目录冻结的是 Mooncakes.io 公共发布注册表，不是赛事 roster；静态源码信号不能证明语义等价、抄袭、原创性或赛事资格。旧快照没有被本报告改日期复用。",
        "",
        "## 当前生产源码哈希",
        "",
        "| 文件 | bytes | SHA-256 |",
        "|---|---:|---|",
    ]
    for item in report["target"]["files"]:
        md.append(f"| `{item['path']}` | {item['bytes']} | `{item['sha256']}` |")
    md += [
        "",
        "## 全量源码读取边界",
        "",
        "ZIP 每个可读文本源码文件均计入行、token 和规范化行集合；ZIP CRC 只在读取时校验。ZIP 内的 zip/tar/gz/xz/7z/rar 仅记录路径与字节，未展开，因此不能写成其内部源码也已比较。",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| 当前坐标 | {report['catalog']['module_count']} |",
        f"| 成功下载 ZIP | {report['artifacts']['download_ok']} |",
        f"| ZIP CRC 可读 | {report['artifacts']['source_ok']} |",
        f"| 读取错误/缺失 | {report['artifacts']['download_errors'] + report['artifacts']['source_errors']} |",
        f"| 源码文件 | {report['artifacts']['source_files']} |",
        f"| 源码字节 | {report['artifacts']['source_bytes']} |",
        f"| 未展开嵌套容器 | {report['artifacts']['nested_container_total']} |",
        "",
        "## 规范信号最高的 30 个包",
        "",
        "| 包 | 形状 token 包含率 | 规范行包含率 | 完整文件 SHA 命中 | 未展开容器 |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in top:
        md.append(
            f"| `{item['name']}@{item['version']}` | {item.get('shape_token_containment', 0):.4f} | {item.get('canonical_line_containment', 0):.4f} | {len(item.get('exact_file_hits', []))} | {item.get('nested_container_count', 0)} |"
        )
    md += [
        "",
        "## 判读限制",
        "",
        "- `exact_file_hits=0` 只说明本次读取到的发布文件没有与当前三个生产文件完全相同的 SHA-256；它不是零相似或资格证明。",
        "- token/规范行包含率只作人工复核排序；公共 API、测试样板、标准协议词汇和独立实现都会产生交集。",
        "- 公共目录不包含未发布、私有或未登记赛事项目；审计不能替代组委会判重。",
        "- 当前记录固定的是 0.2.0 提交后的源码树；若再次提交代码，必须重新冻结目录和重算本报告。",
        "",
    ]
    (out_dir / "audit.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=pathlib.Path, default=ROOT / "outputs/mooncakes-public-comparison-2026-10-27")
    parser.add_argument("--work-dir", type=pathlib.Path, default=ROOT / "work/mooncakes-snapshot-2026-10-27")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--scan-workers", type=int, default=8)
    parser.add_argument(
        "--manifest-limit",
        type=int,
        default=100,
        help="number of coordinates for which to refresh the slower manifest endpoint (0 disables it)",
    )
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = args.work_dir / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    raw = fetch(MODULES_URL)
    raw_path = args.work_dir / "modules.json"
    raw_path.write_bytes(raw)
    modules = json.loads(raw.decode("utf-8"))
    if not isinstance(modules, list):
        raise RuntimeError("Mooncakes modules endpoint did not return a list")
    (args.out_dir).mkdir(parents=True, exist_ok=True)
    (args.out_dir / "catalog-modules.json").write_bytes(raw)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        downloads = list(pool.map(lambda module: download_one(module, archive_dir), modules))
    archive_map = {(x["name"], x["version"]): x for x in downloads if x.get("download_status") == "ok"}
    manifest_modules = modules[: max(0, args.manifest_limit)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(4, min(args.workers, 16))) as pool:
        manifests = list(pool.map(lambda module: manifest_one(module, archive_map), manifest_modules))
    requested_keys = {(item["name"], item["version"]) for item in manifest_modules}
    manifests.extend(
        {
            "name": module["name"],
            "version": module["version"],
            "manifest_status": "not_requested",
            "reason": "manifest endpoint refresh bounded by --manifest-limit",
        }
        for module in modules
        if (module["name"], module["version"]) not in requested_keys
    )
    target, target_sets = target_signals(ROOT)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.scan_workers)) as pool:
        records = list(pool.map(lambda item: scan_archive(item, target_sets), downloads))
    for item in records:
        item["manifest"] = next((m for m in manifests if m["name"] == item.get("name") and m["version"] == item.get("version")), None)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    ok_downloads = [x for x in downloads if x.get("download_status") == "ok"]
    source_ok = [x for x in records if x.get("source_status") == "ok"]
    manifest_matches = [x for x in manifests if x.get("checksum_match")]
    manifest_errors = [x for x in manifests if x.get("manifest_status") == "error"]
    report = {
        "schema": "moon-jmap-mooncakes-freeze-v1",
        "captured_at": now,
        "repository_commit": current_commit(),
        "scope": "Mooncakes.io public published registry; not an official contest roster",
        "catalog": {"endpoint": MODULES_URL, "raw_path": str(raw_path), "raw_sha256": sha256(raw), "module_count": len(modules)},
        "target": target,
        "artifacts": {
            "download_ok": len(ok_downloads),
            "download_errors": len(downloads) - len(ok_downloads),
            "archive_bytes": sum(int(x.get("archive_bytes", 0)) for x in ok_downloads),
            "manifest_matches": len(manifest_matches),
            "manifest_mismatches": sum(1 for x in manifests if x.get("manifest_status") == "ok" and not x.get("checksum_match")),
            "manifest_errors": len(manifest_errors),
            "manifest_not_requested": sum(1 for x in manifests if x.get("manifest_status") == "not_requested"),
            "source_ok": len(source_ok),
            "source_errors": sum(1 for x in records if x.get("source_status") == "error"),
            "source_files": sum(int(x.get("source_files", 0)) for x in source_ok),
            "source_bytes": sum(int(x.get("source_bytes", 0)) for x in source_ok),
            "nested_container_total": sum(int(x.get("nested_container_count", 0)) for x in source_ok),
        },
        "method": {
            "source_files": TARGET_FILES,
            "signals": ["per-file SHA-256", "canonical source lines", "20-token exact shingles", "20-token shape shingles"],
            "manifest_refresh_scope": f"first {max(0, args.manifest_limit)} coordinates by frozen catalog order; all downloaded ZIPs have local SHA-256",
            "third_party_execution": False,
        },
        "limitations": [
            "Public Mooncakes coordinates are not an official contest roster.",
            "Unreadable, unavailable and nested-container source is not represented as inspected source.",
            "Lexical and hash evidence cannot establish semantic equivalence, plagiarism, originality or eligibility.",
        ],
    }
    write_report(args.out_dir, report, records)
    (args.work_dir / "manifest.json").write_text(json.dumps(manifests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.work_dir / "records.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in records), encoding="utf-8")
    print(json.dumps({"status": "complete", "modules": len(modules), "download_ok": len(ok_downloads), "source_ok": len(source_ok), "nested_containers": report["artifacts"]["nested_container_total"], "out_dir": str(args.out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
