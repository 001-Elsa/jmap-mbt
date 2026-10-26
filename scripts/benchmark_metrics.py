#!/usr/bin/env python3
"""Generate deterministic, domain-specific JMAP view metrics.

This harness consumes the repository's *synthetic incremental vectors*.  It is
an evidence tool for the bounded Email/query view state machine, rather than a
network benchmark: no HTTP, authentication, server timing, or live service is
involved.  Each wire-like vector event is projected into the redacted trace
schema in ``docs/trace-schema.md`` and aggregated into counters that explain
why a response could or could not commit a view.

The output deliberately separates:

* ``requests_planned``: calls implied by a plan event;
* ``responses_accepted``/``responses_dropped``: synthetic responses consumed;
* ``response_bytes``: only source-provided fixture bytes; absent values remain ``null``;
* ``query_rebuilds``/``email_rebuilds``: full reconciliation triggers;
* ``budget_termination``: work prevented by a declared vector budget.

No metric should be interpreted as live-server latency, throughput, or
interoperability evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "tests" / "vectors" / "incremental_cases.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "metrics"
TRACE_VERSION = 2

WIRE_METHODS = {
    "query_result": "Email/query",
    "query_changes": "Email/queryChanges",
    "query_fill": "Email/query",
    "query_changes_invalid": "Email/queryChanges",
    "email_changes": "Email/changes",
    "email_changes_invalid": "Email/changes",
    "email_get": "Email/get",
    "stale_response": "Email/queryChanges",
}


def canonical(value: Any) -> bytes:
    """Canonical UTF-8 JSON used for stable byte and hash measurements."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def fixture_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


ACCOUNT_SCOPE = {"service": "synthetic-jmap", "account": "acct-01"}
QUERY_KEY = {
    "mailbox": "mbox-inbox",
    "unread_only": False,
    "sort": "receivedAt:desc",
    "collapse_threads": False,
}
ACCOUNT_SCOPE_HASH = digest(ACCOUNT_SCOPE)
QUERY_KEY_HASH = digest(QUERY_KEY)
RUN_ID = "synthetic-" + digest({
    "fixture_namespace": "moon-jmap-incremental-vectors",
    "trace_version": TRACE_VERSION,
    "account_scope_hash": ACCOUNT_SCOPE_HASH,
    "query_key_hash": QUERY_KEY_HASH,
})[7:23]


def _hash_ids(ids: Iterable[str]) -> str:
    return digest(list(ids))


def _redacted_pending(values: Iterable[str]) -> list[str]:
    """Remove raw message IDs from pending-work trace snapshots."""

    result: list[str] = []
    for value in sorted(set(values)):
        if value.startswith("get:"):
            ids = [item for item in value[4:].split(",") if item]
            result.append("get_hash:" + _hash_ids(ids))
        else:
            result.append(value)
    return result


@dataclass
class Projection:
    """Small trace-only projection of one bounded view.

    This intentionally mirrors only the observable contract.  It does not
    replace the MoonBit implementation and does not claim implementation
    parity; its job is to make metric accounting inspectable and deterministic.
    """

    generation: int
    ordered_ids: list[str]
    total: int
    query_state: str | None
    email_state: str | None
    prefix_limit: int = 50
    completeness: str = "Pending"
    pending_work: list[str] = field(default_factory=list)
    objects: set[str] = field(default_factory=set)
    email_history_invalid: bool = False
    query_history_invalid: bool = False

    def snapshot(self) -> dict[str, Any]:
        body = {
            "ordered_count": len(self.ordered_ids),
            "total": self.total,
            "query_state": self.query_state,
            "email_state": self.email_state,
            "completeness": self.completeness,
            "pending_work": _redacted_pending(self.pending_work),
            "object_count": len(self.objects),
            "ordered_ids_hash": _hash_ids(self.ordered_ids),
            "object_ids_hash": _hash_ids(sorted(self.objects)),
        }
        body["state_hash"] = digest(body)
        return body

    def apply_event(self, event: dict[str, Any], decision: str) -> None:
        kind = event["kind"]
        if kind == "generation_switch":
            self.generation = int(event["to_generation"])
            return
        if kind == "query_result":
            self.query_state = event["query_state"]
            self.ordered_ids = list(event.get("ids", []))[: self.prefix_limit]
            self.total = int(event.get("total", len(self.ordered_ids)))
        elif kind == "query_changes":
            removed = set(event.get("removed", []))
            self.ordered_ids = [item for item in self.ordered_ids if item not in removed]
            for addition in sorted(event.get("added", []), key=lambda item: item["index"]):
                identifier = addition["id"]
                self.ordered_ids = [item for item in self.ordered_ids if item != identifier]
                index = max(0, min(int(addition["index"]), len(self.ordered_ids)))
                self.ordered_ids.insert(index, identifier)
            self.ordered_ids = self.ordered_ids[: self.prefix_limit]
            self.query_state = event.get("to_state", self.query_state)
            self.total = int(event.get("total", self.total))
            if event.get("requires_reconcile"):
                self.pending_work.append("query-recheck")
        elif kind == "query_fill":
            # A fill from another state cannot be mixed into the prior prefix.
            if event.get("state") != self.query_state:
                if decision == "NeedsRefresh":
                    self.pending_work.append("refresh:fill_query_state_mismatch")
                    self.completeness = "NeedsRefresh"
                return
            position = max(0, int(event.get("position", len(self.ordered_ids))))
            ids = list(event.get("ids", []))
            # The fixture uses a suffix fill.  Replace the suffix from position
            # while preserving the already-confirmed prefix.
            self.ordered_ids = (self.ordered_ids[:position] + ids)[: self.prefix_limit]
            self.query_state = event.get("state", self.query_state)
            self.total = int(event.get("total", self.total))
        elif kind == "email_changes":
            self.email_state = event.get("to_state", self.email_state)
        elif kind == "email_get":
            observed = event.get("state", self.email_state)
            # A get response cannot jump over an invalidated or newer
            # Email/changes state.  Keep the covered state and mark the gap.
            if self.email_history_invalid:
                self.pending_work.append("email-history-invalid")
            elif self.email_state is not None and observed != self.email_state:
                self.pending_work.append("email-state-gap")
                self.completeness = "NeedsRefresh"
            else:
                self.email_state = observed
            self.objects.update(event.get("objects", {}).keys())
        elif kind == "email_changes_invalid":
            self.email_state = None
            self.email_history_invalid = True
            self.pending_work.append("email-history-invalid")
        elif kind == "query_changes_invalid":
            self.query_state = None
            self.query_history_invalid = True
            self.pending_work.append("query-history-invalid")
        elif kind == "stale_response":
            # Dropped responses must leave every state field unchanged.
            return

        if decision == "Continue":
            self.completeness = "Pending"
        elif decision == "NeedsRefresh":
            self.completeness = "NeedsRefresh"
            if not self.pending_work:
                self.pending_work.append("refresh:response_requires_reconciliation")
        elif decision == "Pending":
            self.completeness = "Pending"
            if not self.pending_work:
                self.pending_work.append("pending:continue")
        elif decision == "Commit":
            self.completeness = "Ready"
            self.pending_work = []


def _method_event(event: dict[str, Any]) -> str | None:
    return WIRE_METHODS.get(event.get("kind"))


def _decision_for(
    case: dict[str, Any],
    event: dict[str, Any],
    *,
    is_final_wire_event: bool,
    budget_blocked: bool = False,
) -> tuple[str, str]:
    if budget_blocked:
        return "Pending", "budget_exhausted_before_response"
    kind = event.get("kind")
    if kind == "stale_response":
        return "Dropped", "stale_response_discarded"
    if kind == "capabilities":
        return "Unsupported", "fixed_query_projection_not_supported"
    if kind in {"email_changes_invalid", "query_changes_invalid"}:
        reason = "email_history_invalid" if kind.startswith("email") else "query_history_invalid"
        return "NeedsRefresh", reason
    if kind == "query_fill" and event.get("state") != case["view"].get("query_state") and case["id"] == "C05":
        return "NeedsRefresh", "fill_query_state_mismatch"
    expected = case.get("expected", {})
    expected_status = expected.get("status")
    if is_final_wire_event:
        if expected_status == "NeedsRefresh":
            return "NeedsRefresh", str(expected.get("reason", "refresh_required"))
        if expected_status == "Unsupported":
            return "Unsupported", str(expected.get("reason", "unsupported"))
        if expected_status == "Pending":
            return "Pending", str(expected.get("reason", "work_remains"))
        if expected_status == "Ready":
            return "Commit", "view_complete"
    return "Continue", "response_accepted"


def _source_bytes(event: dict[str, Any]) -> int | None:
    """Read bytes only when the fixture explicitly supplies a measurement.

    The current vectors intentionally contain no wire byte counts.  Returning
    ``None`` prevents canonical fixture JSON length from being mistaken for a
    network payload size.
    """

    value = event.get("response_bytes", event.get("bytes"))
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _event_summary(event: dict[str, Any], method: str | None, size: int | None) -> dict[str, Any]:
    kind = event.get("kind")
    summary: dict[str, Any] = {
        "method": method,
        "kind": kind,
        "bytes": size,
        "bytes_source": "fixture" if size is not None else "unavailable",
    }
    if kind in {"query_changes", "query_changes_invalid"}:
        summary.update(
            {
                "old_state": event.get("from_state"),
                "new_state": event.get("to_state"),
                "removed_count": len(event.get("removed", [])),
                "added_count": len(event.get("added", [])),
                "total": event.get("total"),
            }
        )
    elif kind == "query_result":
        summary.update(
            {
                "old_state": None,
                "new_state": event.get("query_state"),
                "ids_count": len(event.get("ids", [])),
                "total": event.get("total"),
            }
        )
    elif kind == "query_fill":
        summary.update(
            {
                "old_state": event.get("state"),
                "new_state": event.get("state"),
                "position": event.get("position"),
                "ids_count": len(event.get("ids", [])),
                "total": event.get("total"),
            }
        )
    elif kind in {"email_changes", "email_changes_invalid"}:
        summary.update(
            {
                "old_state": event.get("from_state"),
                "new_state": event.get("to_state"),
                "created_count": len(event.get("created", [])),
                "updated_count": len(event.get("updated", [])),
                "destroyed_count": len(event.get("destroyed", [])),
                "has_more": bool(event.get("has_more", False)),
            }
        )
    elif kind == "email_get":
        objects = event.get("objects", {})
        summary.update(
            {
                "old_state": None,
                "new_state": event.get("state"),
                "requested_count": len(objects) + len(event.get("notFound", [])),
                "list_count": len(objects),
                "not_found_count": len(event.get("notFound", [])),
            }
        )
    elif kind == "stale_response":
        summary.update({"old_state": event.get("from_state"), "new_state": event.get("to_state")})
    return summary


def _planned_calls(case: dict[str, Any], event: dict[str, Any]) -> int:
    """Estimate calls from a plan metadata event, preserving split semantics."""

    methods = list(event.get("methods", []))
    if not methods:
        return 0
    ids = list(event.get("ids", []))
    max_objects = None
    for prior in case.get("events", []):
        if prior.get("kind") == "limits" and prior.get("maxObjectsInGet"):
            max_objects = int(prior["maxObjectsInGet"])
    total = 0
    for method in methods:
        if method == "Email/get" and ids and max_objects:
            total += (len(ids) + max_objects - 1) // max_objects
        else:
            total += 1
    return total


def run_case(case: dict[str, Any], *, fixture_sha: str) -> dict[str, Any]:
    view = case["view"]
    initial_ids = list(view.get("ordered_ids", []))
    initial_total = int(view.get("total", len(initial_ids)))
    initial_objects = set(view.get("objects", {}).keys())
    initial_complete = bool(
        view.get("query_state")
        and view.get("email_state")
        and len(initial_ids) == min(int(view.get("prefix_limit", 50)), initial_total)
        and set(initial_ids).issubset(initial_objects)
    )
    projection = Projection(
        generation=int(view.get("generation", 0)),
        ordered_ids=initial_ids,
        total=initial_total,
        query_state=view.get("query_state"),
        email_state=view.get("email_state"),
        prefix_limit=int(view.get("prefix_limit", 50)),
        completeness="Ready" if initial_complete else "Pending",
        objects=initial_objects,
    )
    counters: Counter[str] = Counter()
    by_method: dict[str, Counter[str]] = {}
    trace: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    limits: dict[str, int] = {}
    capabilities: dict[str, Any] = {
        "supportsFilter": True,
        "supportsSort": True,
        "supportsResultReference": True,
    }
    planned = 0
    planned_by_method: Counter[str] = Counter()
    budget_termination: dict[str, Any] | None = None
    wire_events = [event for event in case.get("events", []) if _method_event(event)]
    final_wire_index = len(wire_events) - 1
    wire_index = 0
    request_id = 0
    accepted_rounds = 0
    generated_steps = 0
    for event in case.get("events", []):
        kind = event.get("kind")
        if kind in {"limits", "budget", "plan", "generation_switch", "capabilities"}:
            before = projection.snapshot()
            if kind == "limits":
                for key, value in event.items():
                    if key != "kind" and isinstance(value, int):
                        limits[key] = value
                summary = {key: value for key, value in event.items() if key != "kind"}
                reason_code = "limits_declared"
            elif kind == "budget":
                for key, value in event.items():
                    if key != "kind" and isinstance(value, int):
                        limits[key] = value
                summary = {key: value for key, value in event.items() if key != "kind"}
                reason_code = "budget_declared"
            elif kind == "plan":
                plan_calls = _planned_calls(case, event)
                planned += plan_calls
                methods = list(event.get("methods", []))
                plan_ids = list(event.get("ids", []))
                max_objects = limits.get("maxObjectsInGet")
                for method_name in methods:
                    if method_name == "Email/get" and plan_ids and max_objects:
                        planned_by_method[method_name] += (len(plan_ids) + max_objects - 1) // max_objects
                    else:
                        planned_by_method[method_name] += 1
                summary = {key: value for key, value in event.items() if key not in {"kind", "ids"}}
                if event.get("ids"):
                    summary["ids_hash"] = _hash_ids(event["ids"])
                reason_code = "plan_declared"
                if max_objects and event.get("ids"):
                    # A budget-limited plan exposes only the first batch in its
                    # bounded view and records the remainder as pending.
                    selected = list(event["ids"])[:max_objects]
                    projection.ordered_ids = selected[: projection.prefix_limit]
                    projection.objects.intersection_update(projection.ordered_ids)
                    remainder = list(event["ids"])[max_objects:]
                    if remainder:
                        projection.pending_work.append("get:" + ",".join(remainder))
                        projection.completeness = "Pending"
            elif kind == "generation_switch":
                projection.apply_event(event, "Continue")
                summary = {"from_generation": event.get("from_generation"), "to_generation": event.get("to_generation")}
                reason_code = "generation_switched"
            else:
                # No response is issued when required fixed capabilities are absent.
                capabilities.update({key: value for key, value in event.items() if key != "kind"})
                summary = dict(capabilities)
                projection.completeness = "Unsupported"
                counters["unsupported"] += 1
                reason_code = "fixed_query_projection_not_supported"
            after = projection.snapshot()
            controls.append({
                "kind": kind,
                "summary": summary,
                "decision": "Control",
                "reason_code": reason_code,
                "before": before,
                "after": after,
            })
            continue
        method = _method_event(event)
        if method is None:
            continue
        # A round budget is checked before issuing the next request.  C14
        # intentionally contains a second change that cannot be sent after the
        # declared one-round budget.
        round_limit = limits.get("max_rounds")
        if round_limit is None:
            round_limit = limits.get("maxRounds")
        if round_limit is not None and accepted_rounds >= round_limit:
            if budget_termination is None:
                budget_termination = {
                    "reason": "round_budget_exhausted",
                    "limit": round_limit,
                    "used": accepted_rounds,
                    "blocked_event": kind,
                }
                counters["budget_terminations"] += 1
                projection.pending_work.append("budget:round")
                projection.completeness = "Pending"
            continue
        request_id += 1
        wire_index += 1
        generated_steps += 1
        size = _source_bytes(event)
        before = projection.snapshot()
        decision, reason = _decision_for(
            case,
            event,
            is_final_wire_event=(wire_index - 1 == final_wire_index),
        )
        # A stale response carries its own old generation and must never alter
        # state; all other synthetic responses advance one accepted round.
        if decision != "Dropped":
            accepted_rounds += 1
            counters["responses_accepted"] += 1
            if size is not None:
                counters["response_bytes"] += size
                counters["response_bytes_known"] += 1
        else:
            counters["responses_dropped"] += 1
            counters["stale_responses_dropped"] += 1
        projection.apply_event(event, decision)
        after = projection.snapshot()
        if method not in by_method:
            by_method[method] = Counter()
        method_counts = by_method[method]
        method_counts["responses"] += 1
        if size is not None:
            method_counts["bytes"] += size
            method_counts["bytes_known"] += 1
        if decision == "Dropped":
            method_counts["dropped"] += 1
        else:
            method_counts["accepted"] += 1
        # Domain counters are kept separate from request counts.
        if kind == "email_get":
            objects = event.get("objects", {})
            counters["objects_received"] += len(objects)
            counters["requested_objects"] += len(objects) + len(event.get("notFound", []))
            counters["not_found_objects"] += len(event.get("notFound", []))
                # Counter cannot serialise a set; retain it in a private side key.
            current = counters.get("_object_ids", set())
            if not isinstance(current, set):
                current = set()
            current.update(objects)
            counters["_object_ids"] = current
        if kind in {"query_changes", "query_changes_invalid"}:
            counters["query_removed"] += len(event.get("removed", []))
            counters["query_added"] += len(event.get("added", []))
        if kind in {"email_changes", "email_changes_invalid"}:
            counters["email_created"] += len(event.get("created", []))
            counters["email_updated"] += len(event.get("updated", []))
            counters["email_destroyed"] += len(event.get("destroyed", []))
            if event.get("has_more"):
                counters["email_changes_pages"] += 1
        if kind in {"query_result", "query_changes_invalid"}:
            counters["query_rebuilds"] += 1
        if kind == "email_changes_invalid":
            counters["email_rebuilds"] += 1
        if kind == "query_fill":
            counters["query_fill_requests"] += 1
        if kind == "query_changes" and event.get("requires_reconcile"):
            counters["query_reconciliation_required"] += 1
        response_summary = _event_summary(event, method, size)
        call_id = f"synthetic-{case['id']}-{request_id}"
        trace.append(
            {
                "trace_version": TRACE_VERSION,
                "run_id": RUN_ID,
                "scenario_id": case["id"],
                "implementation": "vector-projection",
                "evidence": "synthetic-local",
                "fixture_sha256": fixture_sha,
                "account_scope_hash": ACCOUNT_SCOPE_HASH,
                "query_key_hash": QUERY_KEY_HASH,
                "generation": projection.generation,
                "step": generated_steps,
                "ticket": {
                    "request_id": request_id,
                    "kind": method,
                    "expected_query_state": before["query_state"],
                    "expected_email_state": before["email_state"],
                    "position": event.get("position", 0),
                    "limit": event.get("limit", view.get("prefix_limit", 0)),
                },
                "response": {
                    "call_id": call_id,
                    **response_summary,
                },
                "decision": decision,
                "reason_code": reason,
                "before": before,
                "after": after,
            }
        )
    # A max-calls budget can terminate a plan before a response exists.  The
    # vectors intentionally encode this as plan+budget metadata (C12).
    max_calls = limits.get("max_calls")
    if max_calls is not None and planned > max_calls and budget_termination is None:
        budget_termination = {
            "reason": "call_budget_exhausted",
            "limit": max_calls,
            "planned": planned,
            "used": max_calls,
        }
        counters["budget_terminations"] += 1
        projection.pending_work.append("budget:call")
        projection.completeness = "Pending"
    # Check every expected semantic field before applying an explicit status
    # for control-only vectors.  A metrics run must fail loudly if its
    # projection drifts from the fixture contract.
    expected = case.get("expected", {})
    if "ordered_ids" in expected and projection.ordered_ids != expected["ordered_ids"]:
        raise AssertionError(f"{case['id']}: ordered_ids projection diverged")
    for token in ("query_state", "email_state"):
        if token in expected and getattr(projection, token) != expected[token]:
            raise AssertionError(f"{case['id']}: {token} projection diverged")
    if "generation" in expected and projection.generation != expected["generation"]:
        raise AssertionError(f"{case['id']}: generation projection diverged")
    if expected.get("remaining_ids"):
        pending_text = " ".join(projection.pending_work)
        for identifier in expected["remaining_ids"]:
            if identifier not in pending_text:
                raise AssertionError(f"{case['id']}: remaining id is not pending")
    if expected.get("reason"):
        expected_reason = expected["reason"]
        observed_reason = None
        if budget_termination is not None:
            observed_reason = budget_termination["reason"]
        elif trace:
            observed_reason = trace[-1]["reason_code"]
        elif controls:
            observed_reason = controls[-1]["reason_code"]
        # C12's vector uses the user-facing umbrella name while the metric
        # separates call and round budgets.
        if expected_reason == "budget_exhausted":
            allowed = {"call_budget_exhausted", "round_budget_exhausted"}
        else:
            allowed = {expected_reason}
        if observed_reason not in allowed:
            raise AssertionError(f"{case['id']}: terminal reason diverged: {observed_reason!r}")
    # The projection itself must reach the fixture's terminal status.  Do not
    # overwrite a divergent result with expected.status after the fact.
    expected_status = expected.get("status")
    if expected_status and projection.completeness != expected_status:
        raise AssertionError(
            f"{case['id']}: status projection diverged: {projection.completeness!r}"
        )
    # Remove the private set before serialising.
    object_ids = counters.pop("_object_ids", set())
    counters["unique_objects_received"] = len(object_ids)
    counters["requests_planned"] = planned
    counters["responses_observed"] = counters.get("responses_accepted", 0) + counters.get("responses_dropped", 0)
    counters["responses_total"] = counters["responses_observed"]
    counters["requests_attempted"] = counters["responses_observed"]
    counters["rounds_accepted"] = accepted_rounds
    counters["control_events"] = len(controls)
    # A missing source measurement is represented explicitly as null, never as
    # zero.  This prevents a fixture length or an absent field from becoming a
    # fake wire-byte claim.
    metrics = {key: value for key, value in sorted(counters.items())}
    metrics["requests_planned_by_method"] = dict(sorted(planned_by_method.items()))
    metrics["requests_attempted_definition"] = "one observed response event corresponds to one attempted call; plan-only calls stay in requests_planned"
    known_bytes = counters.get("response_bytes_known", 0)
    metrics["response_bytes"] = counters.get("response_bytes") if known_bytes else None
    metrics["response_bytes_available"] = bool(known_bytes)
    metrics["requests_by_method"] = {
        method: {key: value for key, value in sorted(counts.items())}
        for method, counts in sorted(by_method.items())
    }
    metrics["limits"] = dict(sorted(limits.items()))
    metrics["capabilities"] = dict(sorted(capabilities.items()))
    metrics["account_scope_hash"] = ACCOUNT_SCOPE_HASH
    metrics["query_key_hash"] = QUERY_KEY_HASH
    metrics["budget_termination"] = budget_termination
    if budget_termination is not None:
        terminal_reason_code = budget_termination["reason"]
    elif trace:
        terminal_reason_code = trace[-1]["reason_code"]
    elif expected.get("status") == "Ready":
        # Planning-only vectors have no terminal response; their fixture
        # contract says the existing bounded view is already complete.
        terminal_reason_code = "view_complete"
    elif controls:
        terminal_reason_code = controls[-1]["reason_code"]
    else:
        terminal_reason_code = expected.get("reason")
    metrics["final"] = {
        "status": projection.completeness,
        "reason_code": terminal_reason_code,
        "generation": projection.generation,
        "ordered_count": len(projection.ordered_ids),
        "ordered_ids_hash": _hash_ids(projection.ordered_ids),
        "total": projection.total,
        # The final view exposes only the bounded prefix.  Received objects
        # outside that prefix remain counted in objects_received but are not
        # presented as part of the view projection.
        "object_count": len([item for item in projection.objects if item in projection.ordered_ids]),
        "object_ids_hash": _hash_ids(sorted(item for item in projection.objects if item in projection.ordered_ids)),
        "query_state": projection.query_state,
        "email_state": projection.email_state,
        "pending_work": _redacted_pending(projection.pending_work),
    }
    return {
        "scenario_id": case["id"],
        "title": case.get("title", ""),
        "evidence": "synthetic-local",
        "metrics": metrics,
        "trace": trace,
        "controls": controls,
        "expected": case.get("expected", {}),
    }


def _safe_metrics(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _safe_metrics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_metrics(item) for item in value]
    return value


def run(fixture: Path, output_dir: Path) -> dict[str, Any]:
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    fixture_sha = fixture_digest(fixture)
    cases = payload.get("cases", [])
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = output_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    results = [run_case(case, fixture_sha=fixture_sha) for case in cases]
    # Write one redacted trace per scenario for independent inspection.
    trace_files: list[str] = []
    for result in results:
        path = trace_dir / f"{result['scenario_id']}.json"
        trace_doc = {
            "trace_version": TRACE_VERSION,
            "run_id": RUN_ID,
            "scenario_id": result["scenario_id"],
            "title": result["title"],
            "evidence": "synthetic-local",
            "fixture_sha256": fixture_sha,
            "account_scope_hash": ACCOUNT_SCOPE_HASH,
            "query_key_hash": QUERY_KEY_HASH,
            "capabilities": result["metrics"].get("capabilities", {}),
            "limits": result["metrics"].get("limits", {}),
            "controls": result["controls"],
            "events": result["trace"],
            "final": result["metrics"].get("final", {}),
            "terminal_reason": result["expected"].get("reason"),
        }
        path.write_text(json.dumps(trace_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        trace_files.append(str(path.relative_to(output_dir)))
    aggregate = Counter()
    aggregate_by_method: dict[str, Counter[str]] = {}
    aggregate_planned_by_method: Counter[str] = Counter()
    for result in results:
        for key, value in result["metrics"].items():
            if isinstance(value, int):
                aggregate[key] += value
        for method, counts in result["metrics"].get("requests_by_method", {}).items():
            aggregate_by_method.setdefault(method, Counter()).update(counts)
        aggregate_planned_by_method.update(result["metrics"].get("requests_planned_by_method", {}))
    report = {
        "report_type": "synthetic_jmap_view_metrics",
        "schema_version": 1,
        "generated_on": payload.get("generated_on", "unknown-fixture-date"),
        "evidence": "synthetic-local",
        "live_server": False,
        "performance_claim": False,
        "fixture": str(Path(os.path.relpath(fixture, ROOT))),
        "fixture_sha256": fixture_sha,
        "scenario_count": len(results),
        "trace_version": TRACE_VERSION,
        "run_id": RUN_ID,
        "account_scope_hash": ACCOUNT_SCOPE_HASH,
        "query_key_hash": QUERY_KEY_HASH,
        "capability_projection": {"filter": "mailbox + optional unread", "sort": "receivedAt:desc"},
        "measurement_definition": {
            "requests_attempted": "one observed response event corresponds to one attempted call; plan-only calls stay in requests_planned",
            "response_bytes": "only an explicit response_bytes/bytes field from the fixture; current vectors provide none",
            "objects_received": "Email/get list object count; notFound is counted separately",
            "query_rebuilds": "query_result plus query history invalidation fallback",
            "email_rebuilds": "Email history invalidation fallback",
            "budget_termination": "declared vector max_rounds or max_calls prevents more work",
            "timing": "not measured; no live transport",
            "memory": "not measured; no live transport",
        },
        "aggregate_integer_metrics": dict(sorted(aggregate.items())),
        "aggregate_requests_by_method": {
            method: dict(sorted(counts.items()))
            for method, counts in sorted(aggregate_by_method.items())
        },
        "aggregate_requests_planned_by_method": dict(sorted(aggregate_planned_by_method.items())),
        "aggregate_measurements": {
            "response_bytes": None,
            "response_bytes_available": False,
            "timing": None,
            "memory": None,
        },
        "scenarios": [
            {
                "scenario_id": result["scenario_id"],
                "title": result["title"],
                "metrics": _safe_metrics(result["metrics"]),
                "expected": result["expected"],
                "trace_file": str((trace_dir / f"{result['scenario_id']}.json").relative_to(output_dir)),
            }
            for result in results
        ],
        "trace_files": trace_files,
        "reproducibility": {
            "command": "python3 scripts/benchmark_metrics.py",
            "fixture_sha256": fixture_sha,
            "canonical_json": True,
            "network": False,
            "authentication": False,
        },
    }
    report_path = output_dir / "metrics.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = render_markdown(report)
    (output_dir / "metrics.md").write_text(markdown, encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# MoonJMAP 合成视图指标报告",
        "",
        "> 本报告来自固定增量向量与本地状态投影，只用于解释同步成本和预算行为。它不包含真实 JMAP 服务、网络耗时、吞吐、认证或互操作结论。",
        "",
        f"- fixture：`{report['fixture']}`",
        f"- fixture SHA-256：`{report['fixture_sha256']}`",
        f"- scenario 数：`{report['scenario_count']}`",
        f"- trace schema：`v{report['trace_version']}`",
        "",
        "## 指标定义",
        "",
    ]
    for key, value in report["measurement_definition"].items():
        lines.append(f"- `{key}`：{value}")
    lines.extend(["", "## 汇总", "", "| 指标 | 数值 |", "|---|---:|"])
    for key, value in report["aggregate_integer_metrics"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(["", "## 场景", "", "| 场景 | 状态 | 请求规划数 | 接受响应 | 丢弃响应 | 字节 | 对象 | 重建 | 预算终止 |", "|---|---|---:|---:|---:|---:|---:|---:|---|"])
    for scenario in report["scenarios"]:
        m = scenario["metrics"]
        final = m["final"]
        budget = m.get("budget_termination")
        lines.append(
            f"| `{scenario['scenario_id']}` {scenario['title']} | {final['status']} | "
            f"{m.get('requests_planned', 0)} | {m.get('responses_accepted', 0)} | {m.get('responses_dropped', 0)} | "
            f"{m.get('response_bytes') if m.get('response_bytes_available') else '不可用'} | {m.get('objects_received', 0)} | "
            f"{m.get('query_rebuilds', 0) + m.get('email_rebuilds', 0)} | "
            f"{budget['reason'] if budget else '—'} |"
        )
    lines.extend([
        "",
        "## 证据边界",
        "",
        "每个场景的脱敏逐步 trace 位于 `traces/`。trace 只写方法、状态、计数、哈希和决策原因，不写邮件正文、地址、附件或服务凭据。若需要真实互操作或性能结论，必须另行取得服务版本、脱敏原始响应和网络测量记录。",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    fixture = args.fixture if args.fixture.is_absolute() else ROOT / args.fixture
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    report = run(fixture, output_dir)
    print(output_dir / "metrics.json")
    print(f"scenarios={report['scenario_count']} fixture_sha256={report['fixture_sha256']}")
    for scenario in report["scenarios"]:
        m = scenario["metrics"]
        print(
            f"{scenario['scenario_id']}: status={m['final']['status']} "
            f"accepted={m.get('responses_accepted', 0)} dropped={m.get('responses_dropped', 0)} "
            f"bytes={m.get('response_bytes') if m.get('response_bytes_available') else 'unavailable'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
