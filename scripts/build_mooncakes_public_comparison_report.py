#!/usr/bin/env python3
"""Join the public Mooncakes full static scan and current delta evidence.

The older 3,304-package evidence archive retains per-file hashes and
protocol-feature signals, not generic token fingerprints.  The separate
token audit is therefore limited to the 27 current delta ZIPs.  This script
keeps that boundary explicit and never executes a package.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import zipfile


SIGNAL_KEYS = (
    "jmap", "rfc862x", "capability_urn", "jmap_wire",
    "jmap_reference_state", "jmap_mail_methods", "jmap_mail_fields",
    "mail_protocol", "mail_domain", "json_rpc", "json_pointer", "sse",
    "http_adapter",
)
HIGH_SPECIFIC = ("capability_urn", "jmap_mail_methods")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zjson(zf: zipfile.ZipFile, name: str):
    return json.loads(zf.read(name).decode("utf-8"))


def aggregate_full(evidence: pathlib.Path) -> dict:
    with zipfile.ZipFile(evidence) as zf:
        stats = zjson(zf, "statistics.json")
        rows = zjson(zf, "rows.json")
        catalog_stats = zjson(zf, "catalog/statistics.json")
        modules = zjson(zf, "catalog/modules-end.json")
    sums = collections.Counter()
    nonzero = collections.Counter()
    high = []
    for row in rows:
        sig = row.get("source_signals") or {}
        for key in SIGNAL_KEYS:
            value = int(sig.get(key, 0) or 0)
            sums[key] += value
            nonzero[key] += bool(value)
        if any(int(sig.get(key, 0) or 0) for key in HIGH_SPECIFIC):
            high.append({"module": row.get("模块"), "version": row.get("版本")})
    return {
        "snapshot_modules": len(modules),
        "rows": len(rows),
        "statistics": stats,
        "catalog_statistics": catalog_stats,
        "signal_sums": dict(sums),
        "signal_nonzero_modules": dict(nonzero),
        "high_specific_modules": high,
        "method": "per-file SHA-256 and conservative regex/context scan; no package execution",
    }


def aggregate_delta(scan_dir: pathlib.Path) -> dict:
    # scan-delta.json is the canonical 27-record list.  Older ad-hoc
    # directories sometimes contain one record per JSON, so retain that
    # fallback without treating metadata files as packages.
    records = []
    delta_path = scan_dir / "scan-delta.json"
    if delta_path.exists():
        value = json.loads(delta_path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            records.extend(
                item for item in value
                if isinstance(item, dict) and {"name", "version", "counts"} <= set(item)
            )
    if not records:
        for path in sorted(scan_dir.glob("*.json")):
            if path.name in {"scan-delta.json"}:
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(value, dict) and {"name", "version", "counts"} <= set(value):
                records.append(value)
    sums = collections.Counter()
    nonzero = collections.Counter()
    high = []
    for record in records:
        sig = record.get("counts") or {}
        for key in SIGNAL_KEYS:
            value = int(sig.get(key, 0) or 0)
            sums[key] += value
            nonzero[key] += bool(value)
        if any(int(sig.get(key, 0) or 0) for key in HIGH_SPECIFIC):
            high.append({"module": record.get("name"), "version": record.get("version")})
    return {
        "packages": len(records),
        "archive_bytes": sum(int(r.get("archive_bytes", 0) or 0) for r in records),
        "archive_sha256": {
            f"{r['name']}@{r['version']}": r.get("archive_sha256") for r in records
        },
        "signal_sums": dict(sums),
        "signal_nonzero_modules": dict(nonzero),
        "high_specific_modules": high,
        "method": "per-file SHA-256 and conservative regex/context scan; no package execution",
    }


def similarity_summary(path: pathlib.Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for item in payload.get("comparisons", []):
        rows.append({
            "candidate": item.get("candidate"),
            "triage_score": item.get("triage_score", 0.0),
            "exact_containment": item.get("exact_token_fingerprints", {}).get("target_containment", 0.0),
            "shape_containment": item.get("shape_token_fingerprints", {}).get("target_containment", 0.0),
            "line_containment": item.get("canonical_source_lines", {}).get("target_containment", 0.0),
            "declaration_containment": item.get("declaration_signatures", {}).get("target_containment", 0.0),
            "exact_intersection": item.get("exact_token_fingerprints", {}).get("intersection", 0),
            "shape_intersection": item.get("shape_token_fingerprints", {}).get("intersection", 0),
            "line_intersection": item.get("canonical_source_lines", {}).get("intersection", 0),
        })
    return {
        "audit_sha256": sha256_bytes(path.read_bytes()),
        "candidate_count": payload.get("candidate_count", len(rows)),
        "error_count": payload.get("error_count", 0),
        "target_tree_sha256": (payload.get("target") or {}).get("tree_sha256"),
        "top_by_triage": sorted(rows, key=lambda row: row["triage_score"], reverse=True),
        "method": "20-token exact/shape winnowing, canonical lines and declarations; triage only",
    }


def f(value) -> str:
    return "{:.4f}".format(float(value))


def markdown(payload: dict) -> str:
    full = payload["full_scan"]
    delta = payload["delta_scan"]
    sim = payload["token_similarity_supplement"]
    stats = full["statistics"]
    total = full["signal_sums"].get("capability_urn", 0) + delta["signal_sums"].get("capability_urn", 0)
    methods = full["signal_sums"].get("jmap_mail_methods", 0) + delta["signal_sums"].get("jmap_mail_methods", 0)
    lines = [
        "# MoonJMAP 与 Mooncakes.io 公开全量源码核查（2026-10-26）",
        "",
        "本报告只覆盖 Mooncakes.io 当前公开注册表中可读取的发布 ZIP，不是赛事报名清单。它合并 2026-10-25 的 3,304 包全量静态源码核查与 2026-10-26 新增/变更的 27 包，覆盖当前 3,331 个精确模块版本。",
        "",
        "## 结论",
        "",
        "- 当前公开目录条目数：{}；目录原始 JSON SHA-256：{}。".format(payload["current_modules"], payload["modules_sha256"]),
        "- 全量协议特征源码扫描覆盖：{} 个旧快照包 + {} 个当日增量包 = {} 个当前条目。".format(full["rows"], delta["packages"], payload["covered_current_versions"]),
        "- 全量 JMAP capability URN 命中：{}；标准 JMAP Mail 方法签名命中：{}。".format(total, methods),
        "- 在公开快照和静态方法下，没有观察到可直接替代 MoonJMAP JMAP Core/Mail 交付的协议文本证据；这不是语义等价、代码原创性或赛事判重保证。",
        "",
        "> 这里的“全量”指公开注册表的当前发布坐标和已读取源码证据。历史版本、未发布源码、私有仓库以及赛事提交不在范围内。",
        "",
        "## 证据范围",
        "",
        "| 项目 | 数值 | 证据 |",
        "|---|---:|---|",
        "| 当前目录条目 | {} | work/live-scan-2026-10-26/modules-live.json；SHA-256 {} |".format(payload["current_modules"], payload["modules_sha256"]),
        "| 2025 全量发布 ZIP | {} | 官方 checksum 一致 {}/{} |".format(full["rows"], stats["archives_official_sha256_match"], stats["archives_read"]),
        "| 2025 全量可读文本 | {} | 总字节 {} |".format(stats["total_text_files"], stats["text_bytes"]),
        "| 2025 MoonBit 文件 | {} | 静态读取，不执行 |".format(stats["mbt_files"]),
        "| 2026-10-26 增量 ZIP | {} | manifest/ZIP 27/27 |".format(delta["packages"]),
        "| 当前源码记录覆盖 | {}/{} | work/live-scan-2026-10-26/current-source-coverage.json |".format(payload["covered_current_versions"], payload["current_modules"]),
        "",
        "## 方法边界",
        "",
        "旧快照的全量方法对每个发布 ZIP 的每个可读文件计算 SHA-256，并使用保守协议特征模式保存命中上下文；高召回候选再做人工语义复核。它回答“是否出现 JMAP 专属词法/接口证据”，不能回答任意重命名或重排后的语义等价。",
        "",
        "本次另对 27 个当日 ZIP 运行 scripts/source_similarity_audit.py，计算 20-token 精确/形状归一化 winnowing、规范化源码行和声明签名。旧 3,304 包的归档正文没有保留在当前工作区，因此没有把这套通用 token 指纹倒推到 3,331 个包；下表只能作为 27 包增量补充。",
        "",
        "## 27 个增量包的 token 相似度补充",
        "",
        "- 候选 ZIP：{}；处理错误：{}。".format(sim["candidate_count"], sim["error_count"]),
        "- 机器报告：outputs/mooncakes-delta-source-similarity-2026-10-26/audit.json；SHA-256：{}。".format(sim["audit_sha256"]),
        "",
        "| 包 | 精确 token 包含率 | 形状 token 包含率 | 规范行包含率 | 分流分数 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in sim["top_by_triage"]:
        lines.append("| {} | {} | {} | {} | {} |".format(
            row["candidate"], f(row["exact_containment"]), f(row["shape_containment"]),
            f(row["line_containment"]), f(row["triage_score"])
        ))
    lines += [
        "",
        "分流分数只是人工复核排序信号。公共语言结构、测试样板、依赖接口和独立实现都可能造成交集；本报告没有把任何分数解释为抄袭或原创结论。",
        "",
        "## 全量信号汇总",
        "",
        "| 信号 | 2025 全量命中次数 / 包数 | 2026 增量命中次数 / 包数 |",
        "|---|---:|---:|",
    ]
    for key in SIGNAL_KEYS:
        lines.append("| {} | {} / {} | {} / {} |".format(
            key,
            full["signal_sums"].get(key, 0), full["signal_nonzero_modules"].get(key, 0),
            delta["signal_sums"].get(key, 0), delta["signal_nonzero_modules"].get(key, 0),
        ))
    lines += [
        "",
        "## 不可证明的事项",
        "",
        "- Mooncakes 公共注册表不等于任何赛事的完整参赛名单；没有官方 roster、仓库 URL、commit/ref 或提交归档，就不能声称比对了赛事全部项目。",
        "- 静态词法信号与有限 token 指纹不能证明不存在语义等价实现、独立重写、未发布实现、私有实现或代码复制。",
        "- 没有执行任何第三方包，也没有把 README 单独当成实现证明；ZIP 路径、官方 manifest checksum 和扫描 JSON 均保留供复核。",
        "- 赛事判重仍由章程和评审方决定。",
        "",
        "## 可复核入口",
        "",
        "- work/live-scan-2026-10-26/modules-live.json",
        "- work/live-scan-2026-10-26/current-source-coverage.json",
        "- work/live-scan-2026-10-26/scan-delta.json",
        "- outputs/MoonJMAP-源码核查证据-2026-10-25.zip（3,304 包全量静态证据）",
        "- outputs/mooncakes-delta-source-similarity-2026-10-26/audit.json（27 包 token 补充）",
        "- scripts/source_similarity_audit.py",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default="outputs/MoonJMAP-源码核查证据-2026-10-25.zip")
    parser.add_argument("--scan-dir", default="work/live-scan-2026-10-26")
    parser.add_argument("--similarity", default="outputs/mooncakes-delta-source-similarity-2026-10-26/audit.json")
    parser.add_argument("--out-dir", default="outputs/mooncakes-public-comparison-2026-10-26")
    args = parser.parse_args()
    evidence = pathlib.Path(args.evidence).resolve()
    scan_dir = pathlib.Path(args.scan_dir).resolve()
    similarity_path = pathlib.Path(args.similarity).resolve()
    out_dir = pathlib.Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    coverage = json.loads((scan_dir / "current-source-coverage.json").read_text())
    snapshot = json.loads((scan_dir / "snapshot-report.json").read_text())
    full = aggregate_full(evidence)
    delta = aggregate_delta(scan_dir)
    sim = similarity_summary(similarity_path)
    payload = {
        "schema": "moonjmap.mooncakes_public_comparison.v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "Mooncakes.io public registry current published ZIPs; not a contest roster",
        "current_modules": int(snapshot["snapshot"]["current_modules"]),
        "modules_sha256": snapshot["raw_hashes"]["modules-live.json"],
        "covered_current_versions": int(coverage["current_versions_source_records"]),
        "coverage": coverage,
        "full_scan": full,
        "delta_scan": delta,
        "token_similarity_supplement": sim,
        "inputs": {
            "evidence_zip": str(evidence),
            "evidence_zip_sha256": sha256_bytes(evidence.read_bytes()),
            "scan_dir": str(scan_dir),
            "similarity_json": str(similarity_path),
        },
        "limits": [
            "The full 3,304-package scan records protocol-feature signals and file hashes, not token fingerprints.",
            "General token similarity was run only for the 27 current delta ZIPs whose source was retained.",
            "Mooncakes public registry is not a contest roster.",
            "Static scans and lexical fingerprints do not establish semantic equivalence, plagiarism, originality, or contest eligibility.",
        ],
    }
    (out_dir / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (out_dir / "report.md").write_text(markdown(payload))
    print(json.dumps({"out_dir": str(out_dir), "current_modules": payload["current_modules"], "covered": payload["covered_current_versions"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
