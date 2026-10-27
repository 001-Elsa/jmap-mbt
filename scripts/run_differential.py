#!/usr/bin/env python3
"""Run the deterministic MoonBit/Python incremental-state trace comparison.

The adapter is generated from ``tests/vectors/incremental_cases.json`` and
then executed as a real MoonBit ``moon run --target wasm`` program.  It prints
one projection after every vector event.  This runner independently replays
the same events with ``examples.replay_vectors.Replay`` and compares the
common projection (ordered IDs, opaque states and generation), plus the
scenario-specific plan contract.

This is intentionally *not* a claim of full implementation equivalence: the
Python fixture oracle and the production core have different abstractions for
implicit reconciliation and budget checkpoints.  Those bounded differences
are listed in ``KNOWN_BOUNDARIES`` and emitted in the machine-readable report.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIXTURE = ROOT / "tests" / "vectors" / "incremental_cases.json"
GENERATOR = ROOT / "scripts" / "generate_differential_adapter.py"
MOON = Path(os.environ.get("MOON") or shutil.which("moon") or Path.home() / ".moon" / "bin" / "moon")
REPORT = ROOT / "outputs" / "MoonJMAP-后缀确认跨实现对拍-2026-10-26.json"

# The core intentionally emits a richer plan than the language-neutral vector
# model.  These are expected method kinds from the generated adapter, indexed
# by case and emitted trace step.  IDs/positions are checked by the parser;
# the map makes accidental changes to the next-request kind visible.
PLAN_METHODS: dict[str, list[list[str]]] = {
    "C01": [["Email/queryChanges"], []],
    "C02": [["Email/query"], ["Email/get"], []],
    "C03": [["Email/get"], []],
    "C04": [[]],
    "C05": [["Email/query"], ["Email/query"]],
    "C06": [["Email/get"], ["Email/get"]],
    "C07": [["Email/query"]],
    "C08": [["Email/get"], ["Email/queryChanges"]],
    "C09": [["Email/changes"]],
    "C10": [[]],
    "C12": [["Email/get"], ["Email/get"]],
    "C14": [["Email/queryChanges"], ["Email/query"], ["Email/query"]],
    "C15": [["Email/get"], ["Email/get"], ["Email/get"]],
}

# These are deliberately reported rather than hidden.  They identify where
# the compact vector oracle does not model the production core's stronger
# state contract, or where the adapter has to bridge an implicit operation.
KNOWN_BOUNDARIES = [
    {
        "case": "C01",
        "steps": [0],
        "field": "status",
        "reason": "The core schedules a query reconciliation before an updated Email/get; the vector has a direct get event, so the adapter inserts a no-op queryChanges response.",
    },
    {
        "case": "C02",
        "steps": [0, 1],
        "field": "status",
        "reason": "The core exposes Pending while a short prefix is being filled; the compact oracle leaves status Ready until its synthetic fill event is observed.",
    },
    {
        "case": "C03",
        "steps": [0],
        "field": "status",
        "reason": "The core exposes Pending while the moved ID is awaiting Email/get; the compact oracle omits that transient.",
    },
    {
        "case": "C05",
        "steps": [0],
        "field": "status",
        "reason": "The core exposes Pending while a removed prefix is awaiting its same-state fill; the compact oracle reports Ready for the intermediate delta.",
    },
    {
        "case": "C05",
        "steps": [1],
        "field": "query_state",
        "reason": "The core clears the unusable query token on a cross-state fill; the compact oracle retains q1 as a diagnostic value.",
    },
    {
        "case": "C09",
        "steps": [0],
        "field": "status/reason",
        "reason": "The core keeps an Email/get state gap resumable as Pending with an Email/changes plan; the compact oracle labels it NeedsRefresh/email_state_gap.",
    },
    {
        "case": "C08",
        "steps": [0],
        "field": "reason",
        "reason": "requires_reconcile is a vector annotation; the core exposes the ordinary Pending/get plan before the adapter records the reconciliation requirement.",
    },
    {
        "case": "C12",
        "steps": [1],
        "field": "ordered_ids",
        "reason": "The fixture treats budget exhaustion as a clipped visible prefix. The production core retains the ordered prefix and exposes c in pending_get; the adapter emits the fixture projection to compare the budget boundary.",
    },
    {
        "case": "C15",
        "steps": [0, 1, 2],
        "field": "status",
        "reason": "The vector only checks query lengths. The production core correctly remains Pending until its Email baseline and objects are obtained.",
    },
    {
        "case": "C15",
        "steps": [0, 1, 2],
        "field": "email_state",
        "reason": "C15's expected object is a length-only assertion; it does not describe the core's not-yet-established Email baseline.",
    },
    {
        "case": "C10",
        "steps": [1],
        "field": "reason",
        "reason": "Dropped responses are represented by an unchanged view; the adapter proves the generation guard and does not inject a diagnostic reason into the view.",
    },
    {
        "case": "C14",
        "steps": [0, 1],
        "field": "status",
        "reason": "The compact oracle does not model the core's Pending transient while the budgeted request remains outstanding.",
    },
    {
        "case": "C14",
        "steps": [2],
        "field": "ordered_ids",
        "reason": "After the round budget is exhausted the core refuses the second delta; the compact oracle mutates its list before declaring the budget failure.",
    },
]


def run(cmd: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)


def parse_trace(text: str) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    traces: dict[str, list[dict[str, str]]] = {}
    malformed: list[str] = []
    for line in text.splitlines():
        if not line.startswith(("M|", "P|")):
            continue
        fields = line.split("|")
        kind, case, step = fields[0], fields[1], fields[2]
        item: dict[str, str] = {"kind": kind, "case": case, "step": step}
        if kind == "M" and len(fields) > 3:
            item["status"] = fields[3]
            fields = fields[:3] + fields[4:]
        for field in fields[3:]:
            if "=" in field:
                key, value = field.split("=", 1)
                item[key] = value
        traces.setdefault(case, []).append(item)
        if not case or not step.isdigit():
            malformed.append(line)
    return traces, malformed


def oracle_trace(case: dict[str, Any]) -> list[dict[str, Any]]:
    # Importing the independent model is intentional. It never imports the
    # MoonBit package and remains a separate implementation boundary.
    from examples.replay_vectors import Replay

    replay = Replay(copy.deepcopy(case["view"]))
    out: list[dict[str, Any]] = []
    for event in case.get("events", []):
        replay.apply(event)
        out.append(copy.deepcopy(replay.result()))
    return out


def methods_from_plan(value: str) -> list[str]:
    if not value:
        return []
    return [part.split("#", 1)[0] for part in value.split(";") if part]


def expected_plan(case: str, index: int) -> list[str] | None:
    plans = PLAN_METHODS.get(case)
    if plans is None or index >= len(plans):
        return None
    return plans[index]


def boundary_for(case: str, step: int, field: str) -> bool:
    for item in KNOWN_BOUNDARIES:
        if item["case"] == case and step in item["steps"]:
            if field == item["field"] or field in str(item["field"]).split("/"):
                return True
            if item["field"] == "status/reason" and field in {"status", "reason"}:
                return True
    return False


def compare_case(case: dict[str, Any], actual: list[dict[str, str]]) -> dict[str, Any]:
    cid = case["id"]
    expected = oracle_trace(case)
    issues: list[dict[str, Any]] = []
    compared: list[dict[str, Any]] = []

    m_records = [x for x in actual if x["kind"] == "M"]
    p_records = [x for x in actual if x["kind"] == "P"]
    if cid == "C11":
        got = [methods_from_plan(x.get("plan", "")) for x in p_records]
        want = case["expected"].get("plan_calls", [])
        if got != want:
            issues.append({"field": "plan_calls", "expected": want, "actual": got})
        else:
            compared.append({"field": "plan_calls", "steps": len(got)})
        return {"case": cid, "oracle_steps": len(expected), "moon_steps": len(actual), "passed": not issues, "compared": compared, "issues": issues}

    if cid == "C13":
        if not m_records or m_records[0].get("status") != "Unsupported":
            issues.append({"field": "status", "expected": "Unsupported", "actual": m_records[0] if m_records else None})
        else:
            compared.append({"field": "status", "step": 0})
        return {"case": cid, "oracle_steps": len(expected), "moon_steps": len(actual), "passed": not issues, "compared": compared, "issues": issues}

    # C12's vector has limits/budget/plan events.  The P line is the plan
    # event; the final M line is compared against its compact expected shape.
    if cid == "C12":
        got = [methods_from_plan(x.get("plan", "")) for x in p_records]
        want = ["Email/get"]
        if got != [want]:
            issues.append({"field": "plan", "expected": [want], "actual": got})
        else:
            compared.append({"field": "plan", "step": 0})
        final = next((x for x in m_records if x.get("step") == "1"), None)
        if final:
            if final.get("ids") != "a,b":
                issues.append({"field": "ordered_ids", "expected": "a,b", "actual": final.get("ids")})
            if final.get("pg") != "c":
                issues.append({"field": "pending_get", "expected": "c", "actual": final.get("pg")})
            compared.append({"field": "budget_projection", "step": 1})
        else:
            issues.append({"field": "trace", "expected": "C12 step 1", "actual": None})
        return {"case": cid, "oracle_steps": len(expected), "moon_steps": len(actual), "passed": not issues, "compared": compared, "issues": issues}

    if len(m_records) != len(expected):
        issues.append({"field": "trace_length", "expected": len(expected), "actual": len(m_records)})

    # v0.2 deliberately publishes only the server-confirmed leading prefix
    # while a suffix read is outstanding. Explicit per-scenario expectations
    # check those intermediate states; the oracle still checks final lists.
    confirmed_prefix_steps = {
        ("C02", 0): ["a"],
        ("C05", 0): ["a"],
        ("C05", 1): ["a"],
        ("C14", 1): [],
        ("C14", 2): [],
    }
    for idx, want in enumerate(expected):
        if idx >= len(m_records):
            break
        got = m_records[idx]
        # The language-neutral oracle only publishes fields it knows. Empty
        # optional strings in the MoonBit projection correspond to None.
        fields: list[tuple[str, Any]] = [
            ("ordered_ids", ",".join(confirmed_prefix_steps.get((cid, idx), want.get("ordered_ids", [])))),
            ("query_state", want.get("query_state", "") or ""),
            ("email_state", want.get("email_state", "") or ""),
        ]
        if "generation" in want:
            fields.append(("generation", str(want["generation"])))
        if "status" in want and not boundary_for(cid, idx, "status"):
            fields.append(("status", want["status"]))
        if "reason" in want and not boundary_for(cid, idx, "reason"):
            # Core reasons are intentionally more explanatory. Compare exact
            # names where they are stable, and map the known RFC boundary text.
            reason_map = {
                "query_history_invalid": "query history is no longer available",
                "email_history_invalid": "Email history is no longer available",
                "fill_query_state_mismatch": "prefix fill crossed queryState boundaries",
                "budget_exhausted": "budget_exhausted",
                "round_budget_exhausted": "round budget exhausted",
                "query_changed_during_refresh": "query_changed_during_refresh",
            }
            fields.append(("reason", reason_map.get(want["reason"], want["reason"])))
        for field, expected_value in fields:
            if boundary_for(cid, idx, field) and not (field == "ordered_ids" and (cid, idx) in confirmed_prefix_steps):
                continue
            actual_value = got.get({"ordered_ids": "ids", "query_state": "q", "email_state": "e", "generation": "gen"}.get(field, field), "")
            if actual_value != expected_value:
                issues.append({"field": field, "step": idx, "expected": expected_value, "actual": actual_value})
            else:
                compared.append({"field": field, "step": idx})
        plan_want = expected_plan(cid, idx)
        if plan_want is not None:
            plan_got = methods_from_plan(got.get("plan", ""))
            if plan_got != plan_want:
                issues.append({"field": "plan_methods", "step": idx, "expected": plan_want, "actual": plan_got})
            else:
                compared.append({"field": "plan_methods", "step": idx})

    # C15 intentionally compares its vector's explicit length checks.
    if cid == "C15":
        got_lengths = []
        for item in m_records:
            raw = item.get("len", "0:0")
            total, length = raw.split(":", 1)
            got_lengths.append({"total": int(total), "length": int(length)})
        want_lengths = case["expected"].get("length_checks", [])
        if got_lengths != want_lengths:
            issues.append({"field": "length_checks", "expected": want_lengths, "actual": got_lengths})
        else:
            compared.append({"field": "length_checks", "steps": len(got_lengths)})

    return {"case": cid, "oracle_steps": len(expected), "moon_steps": len(actual), "passed": not issues, "compared": compared, "issues": issues}


def main() -> int:
    generated = run([sys.executable, str(GENERATOR)], timeout=30)
    if generated.returncode != 0:
        print(generated.stdout + generated.stderr, file=sys.stderr)
        return generated.returncode
    if not MOON.exists():
        print(f"moon executable not found: {MOON}", file=sys.stderr)
        return 2
    # Keep regenerated adapter sources consistent with the repository's
    # formatting gate; a successful comparison must not dirty formatted code.
    formatted = run([str(MOON), "fmt", "cmd/differential"], timeout=30)
    if formatted.returncode != 0:
        print(formatted.stdout + formatted.stderr, file=sys.stderr)
        return formatted.returncode
    result = run([str(MOON), "run", "--target", "wasm", "cmd/differential"], timeout=180)
    text = result.stdout + result.stderr
    traces, malformed = parse_trace(text)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    results = [compare_case(case, traces.get(case["id"], [])) for case in data["cases"]]
    passed = sum(1 for item in results if item["passed"])
    report = {
        "report_type": "cross_implementation_incremental_trace",
        "generated_on": "2026-10-26",
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "adapter": "cmd/differential/main.mbt",
        "command": "moon run --target wasm cmd/differential",
        "moon_returncode": result.returncode,
        "trace_cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "malformed_trace_lines": malformed,
        "cases": results,
        "known_boundaries": KNOWN_BOUNDARIES,
        "server_suffix_contract": "C02/C05/C14 intermediate prefixes are explicitly checked under the v0.2 contract. C03/C08 perform an additional same-queryState synthetic server read before comparison. Final oracle lists are still checked; this is not equal per-event behavior to the old local-splice implementation.",
        "evidence_boundary": {
            "compares": ["ordered_ids", "opaque query/email states", "generation", "next-plan method and payload projection", "C15 query length checks"],
            "does_not_prove": ["full cross-language state equivalence", "real-server interoperability", "HTTP/TLS/OAuth", "performance", "wire decoder equivalence"],
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"differential trace: {passed}/{len(results)} cases passed")
    print(REPORT)
    for item in results:
        marker = "PASS" if item["passed"] else "FAIL"
        print(f"{marker} {item['case']} compared={len(item['compared'])} issues={len(item['issues'])}")
        for issue in item["issues"]:
            print("  ", issue)
    return 0 if result.returncode == 0 and not malformed and passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
