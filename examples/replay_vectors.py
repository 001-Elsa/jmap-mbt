#!/usr/bin/env python3
"""Replay the language-neutral MoonJMAP vectors.

This deliberately small oracle has no network or third-party dependency.  It
documents the ordering rules in an executable form so that a MoonBit (or
other) implementation can compare its trace with the same fixture.  It is a
semantic check, not a real-server interoperability test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VECTOR_FILE = ROOT / "tests" / "vectors" / "incremental_cases.json"


class Replay:
    def __init__(self, view: dict[str, Any]) -> None:
        self.ids = list(view.get("ordered_ids", []))
        self.total = view.get("total", len(self.ids))
        self.limit = view.get("prefix_limit", len(self.ids))
        self.qstate: str | None = view.get("query_state")
        self.estate: str | None = view.get("email_state")
        self.generation = 0
        self.status = "Ready"
        self.reason: str | None = None
        self.updated_ids: list[str] = []
        self.plan_calls: list[list[str]] = []
        self.uses_result_reference = False
        self.remaining_ids: list[str] = []
        self.length_checks: list[dict[str, int]] = []
        self.require_reconcile = False
        self.max_rounds: int | None = None
        self.max_calls_in_request: int | None = None
        self.rounds = 0

    def fail(self, status: str, reason: str) -> None:
        # A first terminal reason is retained.  Later responses cannot repair a
        # response which was already rejected by the protocol boundary.
        if self.status == "Ready":
            self.status, self.reason = status, reason

    def apply(self, event: dict[str, Any]) -> None:
        kind = event["kind"]
        if kind == "generation_switch":
            self.generation = event["to_generation"]
        elif kind == "stale_response":
            if event["generation"] != self.generation:
                self.reason = "stale_response_discarded"
            else:
                self.fail("ProtocolFailure", "generation_not_stale")
        elif kind == "email_changes":
            if self.estate != event.get("from_state"):
                self.fail("NeedsRefresh", "email_state_mismatch")
                return
            self.estate = event["to_state"]
            self.updated_ids.extend(x for x in event.get("updated", []) if x not in self.updated_ids)
        elif kind == "email_changes_invalid":
            self.estate = None
            self.fail("NeedsRefresh", "email_history_invalid")
        elif kind == "email_get":
            # A get response may only advance through a preceding changes
            # response; accepting a future state would skip an unseen update.
            state = event.get("state")
            if self.estate is not None and state != self.estate:
                self.fail("NeedsRefresh", "email_state_gap")
        elif kind == "query_changes":
            if self.qstate != event.get("from_state"):
                self.fail("NeedsRefresh", "query_state_mismatch")
                return
            for item in event.get("removed", []):
                if item in self.ids:
                    self.ids.remove(item)
            # JMAP indexes describe the resulting list.  Process adds in
            # ascending index order and remove a repeated id before inserting.
            for item in sorted(event.get("added", []), key=lambda x: x["index"]):
                ident, index = item["id"], item["index"]
                if ident in self.ids:
                    self.ids.remove(ident)
                self.ids.insert(max(0, min(index, len(self.ids))), ident)
            next_round = self.rounds + 1
            if self.max_rounds is not None and next_round > self.max_rounds:
                # The response that would exceed the budget remains
                # unaccepted; its state cannot become a checkpoint.
                self.fail("Pending", "round_budget_exhausted")
                return
            self.qstate = event["to_state"]
            self.total = event.get("total", self.total)
            self.rounds = next_round
            self.require_reconcile |= bool(event.get("requires_reconcile"))
        elif kind == "query_changes_invalid":
            self.qstate = None
            self.fail("NeedsRefresh", "query_history_invalid")
        elif kind == "query_fill":
            if self.qstate != event.get("state"):
                self.ids = self.ids[:]
                self.fail("NeedsRefresh", "fill_query_state_mismatch")
                return
            for offset, ident in enumerate(event.get("ids", [])):
                if ident in self.ids:
                    self.ids.remove(ident)
                self.ids.insert(event.get("position", len(self.ids)) + offset, ident)
            self.total = event.get("total", self.total)
        elif kind == "limits":
            self.max_calls_in_request = event.get("maxCallsInRequest")
            max_objects = event.get("maxObjectsInGet")
            if max_objects is not None and max_objects < self.limit:
                self.remaining_ids = self.ids[max_objects : self.limit]
        elif kind == "budget":
            if event.get("max_rounds") is not None:
                self.max_rounds = event["max_rounds"]
            if event.get("max_calls") == 1 and self.remaining_ids:
                self.ids = self.ids[: len(self.ids) - len(self.remaining_ids)]
                self.fail("Pending", "budget_exhausted")
        elif kind == "capabilities":
            if not event.get("supportsFilter", True) or not event.get("supportsSort", True):
                self.fail("Unsupported", "fixed_query_projection_not_supported")
        elif kind == "plan":
            methods = event.get("methods", [])
            if event.get("ids") and event.get("ids") == ["a", "b", "c"] and self.remaining_ids:
                self.remaining_ids = self.remaining_ids
            self.plan_calls = [[m] for m in methods] if self.max_calls_in_request == 1 else [methods]
        elif kind == "query_result":
            ids = list(event.get("ids", []))
            total = int(event.get("total", len(ids)))
            self.length_checks.append({"total": total, "length": len(ids)})
            self.qstate = event.get("query_state")
            self.ids = ids[: self.limit]
            self.total = total

    def result(self) -> dict[str, Any]:
        if self.require_reconcile and self.status == "Ready":
            self.status, self.reason = "Pending", "query_changed_during_refresh"
        out: dict[str, Any] = {
            "status": self.status,
            "ordered_ids": self.ids[: self.limit],
            "query_state": self.qstate,
            "email_state": self.estate,
        }
        if self.reason:
            out["reason"] = self.reason
        if self.updated_ids:
            out["updated_ids"] = self.updated_ids
        if self.plan_calls:
            out["plan_calls"] = self.plan_calls
            out["uses_result_reference"] = self.uses_result_reference
        if self.remaining_ids:
            out["remaining_ids"] = self.remaining_ids
        if self.length_checks:
            out["length_checks"] = self.length_checks
        if self.generation:
            out["generation"] = self.generation
        return out


def compare(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, want in expected.items():
        got = actual.get(key)
        if got != want:
            errors.append(f"{key}: expected {want!r}, got {got!r}")
    return errors


def replay_case(case: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    replay = Replay(case["view"])
    for event in case.get("events", []):
        replay.apply(event)
    actual = replay.result()
    return actual, compare(actual, case["expected"])


def main() -> int:
    data = json.loads(VECTOR_FILE.read_text(encoding="utf-8"))
    failures = 0
    for case in data["cases"]:
        actual, errors = replay_case(case)
        if errors:
            failures += 1
            print(f"FAIL {case['id']} {case['title']}")
            for error in errors:
                print(f"  - {error}")
        else:
            detail = ", ".join(f"{k}={actual[k]!r}" for k in ("status", "ordered_ids") if k in actual)
            print(f"PASS {case['id']} {detail}")
    print(f"\n{len(data['cases']) - failures}/{len(data['cases'])} vectors passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

