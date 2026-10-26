#!/usr/bin/env python3
"""Derive a redacted object-level JMAP interop record from a live benchmark run.

The benchmark run already contains the HTTP status, wire sizes, state/id hashes,
and typed response summaries.  This utility does not replay requests or invent
responses; it only projects those live observations into an interop-focused
record that makes non-empty Email/get results explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source benchmark must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = load(args.source)
    observations = source.get("observations")
    if not isinstance(observations, list):
        raise ValueError("source benchmark has no observations array")
    metrics = source.get("metrics") if isinstance(source.get("metrics"), dict) else {}
    service = source.get("service") if isinstance(source.get("service"), dict) else {}
    session = source.get("session") if isinstance(source.get("session"), dict) else {}

    method_counts = Counter(str(item.get("method")) for item in observations if isinstance(item, dict))
    successful = [
        item
        for item in observations
        if isinstance(item, dict)
        and isinstance(item.get("status"), int)
        and 200 <= item["status"] < 300
    ]
    jmap_observations = [
        item for item in observations if isinstance(item, dict) and item.get("kind") == "jmap"
    ]

    # Keep the already-redacted summaries and wire hashes.  Never add raw IDs,
    # request/response bodies, credentials, addresses, subjects, or content.
    events = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        events.append(
            {
                "kind": item.get("kind"),
                "method": item.get("method"),
                "url": item.get("url"),
                "status": item.get("status"),
                "elapsed_ms": item.get("elapsed_ms"),
                "request_bytes": item.get("request_bytes"),
                "response_bytes": item.get("response_bytes"),
                "request_sha256": item.get("request_sha256"),
                "response_sha256": item.get("response_sha256"),
                "error": item.get("error"),
                "response": item.get("response"),
            }
        )

    def summaries(method: str) -> list[dict[str, Any]]:
        return [
            item["response"]
            for item in jmap_observations
            if item.get("method") == method and isinstance(item.get("response"), dict)
        ]

    queries = summaries("Email/query")
    gets = summaries("Email/get")
    changes = summaries("Email/changes")
    query_changes = summaries("Email/queryChanges")

    query_counts = [int(item.get("ids_count", 0)) for item in queries]
    query_totals = [item.get("total") for item in queries]
    get_counts = [int(item.get("objects_count", 0)) for item in gets]
    get_not_found = [int(item.get("not_found_count", 0)) for item in gets]
    change_counts = [
        {
            "created": int(item.get("created_count", 0)),
            "updated": int(item.get("updated_count", 0)),
            "destroyed": int(item.get("destroyed_count", 0)),
            "has_more_changes": item.get("has_more_changes"),
        }
        for item in changes
    ]
    query_change_counts = [
        {
            "added": int(item.get("added_count", 0)),
            "removed": int(item.get("removed_count", 0)),
            "total": item.get("total"),
        }
        for item in query_changes
    ]

    output = {
        "schema": "moon-jmap-real-interop-v1",
        "redaction_version": source.get("redaction_version", 1),
        "status": "complete" if source.get("status") == "complete" and not source.get("failures") else "partial",
        "evidence_level": "derived-from-live-http-observations",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "real_service": {
            "product": service.get("product") or "Stalwart Server",
            "version": service.get("version") or "v0.16.27",
            "deployment": service.get("deployment") or "local-real-stalwart",
            "mode": service.get("mode"),
            "endpoint": source.get("endpoint"),
            "api_endpoint": source.get("api_endpoint"),
        },
        "source_artifact": {
            "path": str(args.source),
            "sha256": sha256_file(args.source),
            "status": source.get("status"),
            "performance_claim": source.get("performance_claim"),
        },
        "authentication": source.get("authentication"),
        "session": {
            "http_status": session.get("status"),
            "capabilities": session.get("capabilities", []),
        },
        "transport": {
            "observations": len(observations),
            "successful_2xx": len(successful),
            "jmap_requests": len(jmap_observations),
            "method_counts": dict(sorted(method_counts.items())),
            "failures": source.get("failures", []),
        },
        "method_evidence": {
            "Email/query": {
                "calls": len(queries),
                "all_http_2xx": all(item.get("status") and 200 <= item["status"] < 300 for item in observations if item.get("method") == "Email/query"),
                "ids_count_per_call": query_counts,
                "total_per_call": query_totals,
                "can_calculate_changes": [item.get("can_calculate_changes") for item in queries],
            },
            "Email/get": {
                "calls": len(gets),
                "all_http_2xx": all(item.get("status") and 200 <= item["status"] < 300 for item in observations if item.get("method") == "Email/get"),
                "objects_count_per_call": get_counts,
                "objects_received_total": sum(get_counts),
                "not_found_count_per_call": get_not_found,
                "properties_observed": sorted({prop for item in gets for prop in item.get("properties", [])}),
            },
            "Email/changes": {
                "calls": len(changes),
                "all_http_2xx": all(item.get("status") and 200 <= item["status"] < 300 for item in observations if item.get("method") == "Email/changes"),
                "responses": change_counts,
            },
            "Email/queryChanges": {
                "calls": len(query_changes),
                "all_http_2xx": all(item.get("status") and 200 <= item["status"] < 300 for item in observations if item.get("method") == "Email/queryChanges"),
                "responses": query_change_counts,
            },
        },
        "object_state": {
            "account_id_hash": source.get("account_id_hash"),
            "mailbox_id_hash": source.get("mailbox_id_hash"),
            "query_state_hashes": (source.get("state_frontiers") or {}).get("query_state_hashes", []),
            "email_state_hashes": (source.get("state_frontiers") or {}).get("email_state_hashes", []),
            "state_frontiers_stable": len(set((source.get("state_frontiers") or {}).get("query_state_hashes", []))) <= 1
            and len(set((source.get("state_frontiers") or {}).get("email_state_hashes", []))) <= 1,
        },
        "performance_context": {
            "parameters": source.get("parameters"),
            "metrics": metrics,
            "note": "The timing and byte totals are retained from the live benchmark; this record adds no synthetic measurements.",
        },
        "http_events": events,
        "limitations": [
            "The source run used five synthetic messages already present in the local test mailbox; no raw message body, address, subject, or opaque identifier is retained.",
            "Email/get returned real non-empty objects, while Email/changes and Email/queryChanges exercised valid no-change responses; this run does not evidence a non-empty create/update/destroy delta.",
            "The service was a local loopback Stalwart process. This does not establish compatibility with every JMAP implementation or a hosted production service.",
            "The record is derived from the redacted live benchmark artifact rather than a replay or fake server; credentials and raw HTTP bodies were never written.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": output["status"], "source_sha256": output["source_artifact"]["sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
