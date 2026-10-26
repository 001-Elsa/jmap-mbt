#!/usr/bin/env python3
"""Independent MoonJMAP acceptance oracle.

This file deliberately does not import the MoonBit implementation.  It models
the small, difficult part of MoonJMAP (a bounded ordered Email view) in a
separate implementation and checks the behaviour promised by the re-planned
project.  It is useful before a MoonBit ABI is frozen and remains useful after
that point as a review oracle for the fixtures in ``tests/vectors``.

The oracle is intentionally conservative:

* JMAP states are opaque strings.  They are compared for equality only.
* a view is Ready only when its prefix is complete, its objects are covered,
  and both progress chains have no pending work;
* a response from an older request generation can never mutate the view.

Run ``python3 tests/verify.py`` from the repository root.  Use
``--strict-structure`` in CI once the MoonBit package and its documentation
have been created.  The default mode still runs every oracle scenario when a
developer is working on the scaffold and reports missing paths as warnings.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class Status(str, Enum):
    READY = "Ready"
    PENDING = "Pending"
    NEEDS_REFRESH = "NeedsRefresh"
    UNSUPPORTED = "Unsupported"
    PROTOCOL_FAILURE = "ProtocolFailure"


class OracleFailure(AssertionError):
    """A failure in the independent acceptance model."""


@dataclass(frozen=True)
class Scope:
    service: str
    account: str


@dataclass(frozen=True)
class QueryKey:
    scope: Scope
    mailbox: str
    unread_only: bool = False
    sort: str = "receivedAt:desc"
    collapse_threads: bool = False


@dataclass(frozen=True)
class Email:
    id: str
    subject: str = ""
    keywords: tuple[str, ...] = ()
    preview: str = ""


@dataclass(frozen=True)
class Added:
    id: str
    index: int


@dataclass(frozen=True)
class QueryDelta:
    old_state: str
    new_state: str
    removed: tuple[str, ...] = ()
    added: tuple[Added, ...] = ()
    total: int = 0
    can_calculate_changes: bool = True
    too_many_changes: bool = False


@dataclass(frozen=True)
class EmailDelta:
    old_state: str
    new_state: str
    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    destroyed: tuple[str, ...] = ()
    has_more: bool = False
    can_calculate_changes: bool = True


@dataclass
class View:
    scope: Scope
    query: QueryKey
    prefix_limit: int
    ordered_ids: list[str]
    total: int
    objects: dict[str, Email]
    email_state: str
    query_state: str
    status: Status = Status.PENDING
    pending_work: set[str] = field(default_factory=set)
    generation: int = 0
    error: str | None = None

    @property
    def target_length(self) -> int:
        return min(self.prefix_limit, self.total)

    def checkpoint(self) -> dict[str, Any]:
        """Return an explicit, JSON-safe checkpoint projection.

        This is not the package's serialization format; it is a test oracle
        projection that makes accidental token mixing and incomplete commits
        visible in test failures.
        """

        return {
            "format_version": 1,
            "account_scope": {"service": self.scope.service, "account": self.scope.account},
            "query_key": {
                "mailbox": self.query.mailbox,
                "unread_only": self.query.unread_only,
                "sort": self.query.sort,
                "collapse_threads": self.query.collapse_threads,
            },
            "prefix_limit": self.prefix_limit,
            "ordered_ids": list(self.ordered_ids),
            "total": self.total,
            "objects": sorted(self.objects),
            "email_progress": self.email_state,
            "query_progress": self.query_state,
            "completeness": self.status.value,
            "pending_work": sorted(self.pending_work),
        }


class SyncOracle:
    """Small reference state machine for a bounded JMAP Email view."""

    def __init__(self, view: View):
        if view.prefix_limit < 0:
            raise ValueError("prefix_limit must be non-negative")
        self.view = view

    @classmethod
    def initial(
        cls,
        *,
        scope: Scope,
        query: QueryKey,
        prefix_limit: int,
        ids: Sequence[str],
        total: int,
        query_state: str,
        email_state: str,
        objects: Mapping[str, Email] | None = None,
    ) -> "SyncOracle":
        """Construct a view from an Email/query and Email/get observation.

        ``objects`` may arrive in any order; mapping by ID is required.  IDs
        outside the bounded prefix are deliberately ignored.
        """

        if total < 0:
            raise ValueError("total cannot be negative")
        if len(ids) > min(prefix_limit, total):
            raise ValueError("query returned more IDs than the requested prefix")
        if len(set(ids)) != len(ids):
            raise ValueError("query returned duplicate IDs")
        view = View(
            scope=scope,
            query=query,
            prefix_limit=prefix_limit,
            ordered_ids=list(ids),
            total=total,
            objects={},
            email_state=email_state,
            query_state=query_state,
            status=Status.PENDING,
        )
        oracle = cls(view)
        oracle._recompute_pending()
        oracle.accept_get(objects or {}, request_generation=view.generation)
        return oracle

    def _recompute_pending(self) -> None:
        v = self.view
        # Preserve non-prefix work such as changes pages and a protocol error.
        preserved = {
            p
            for p in v.pending_work
            if p.startswith("changes:")
            or p.startswith("error:")
            or p.startswith("refresh:")
            or p.startswith("get:")
            or p == "query-recheck"
        }
        pending = set(preserved)
        if len(v.ordered_ids) < v.target_length:
            pending.add("query-gap")
        missing = set(v.ordered_ids) - set(v.objects)
        pending.update(f"get:{item}" for item in sorted(missing))
        v.pending_work = pending
        if v.error:
            v.status = Status.PROTOCOL_FAILURE
        elif any(p.startswith("refresh:") for p in pending):
            v.status = Status.NEEDS_REFRESH
        elif pending:
            v.status = Status.PENDING
        else:
            v.status = Status.READY

    def _fail_refresh(self, reason: str) -> None:
        v = self.view
        # Keep the old list for stale display but make the checkpoint plainly
        # unusable as a completed synchronization point.
        v.pending_work.add(f"refresh:{reason}")
        v.status = Status.NEEDS_REFRESH
        v.error = None

    def _fail_protocol(self, reason: str) -> None:
        v = self.view
        v.pending_work.add(f"error:{reason}")
        v.status = Status.PROTOCOL_FAILURE
        v.error = reason

    def issue_ticket(self) -> int:
        self.view.generation += 1
        return self.view.generation

    def accept_get(
        self,
        objects: Mapping[str, Email],
        *,
        request_generation: int,
        not_found: Iterable[str] = (),
        observed_state: str | None = None,
    ) -> bool:
        """Apply an Email/get result, dropping late responses by generation."""

        v = self.view
        if request_generation != v.generation:
            return False
        for item in not_found:
            if item in v.ordered_ids:
                self._fail_refresh(f"notFound:{item}")
            v.objects.pop(item, None)
        for item, obj in objects.items():
            if item != obj.id:
                self._fail_protocol("object-id-mismatch")
                return False
            if item in v.ordered_ids:
                v.objects[item] = obj
                v.pending_work.discard(f"get:{item}")
        # Observation of a newer state is not permission to skip Email/changes.
        if observed_state is not None and observed_state != v.email_state:
            v.pending_work.add(f"changes:{v.email_state}")
        self._recompute_pending()
        return True

    def apply_email_changes(self, delta: EmailDelta, *, request_generation: int) -> bool:
        v = self.view
        if request_generation != v.generation:
            return False
        if not delta.can_calculate_changes:
            self._fail_refresh("email-cannotCalculateChanges")
            return True
        if delta.old_state != v.email_state:
            self._fail_refresh("email-state-context")
            return True
        # A JMAP changes response is allowed to contain overlap among these
        # sets.  Destruction wins for the local object cache.
        destroyed = set(delta.destroyed)
        for item in destroyed:
            v.objects.pop(item, None)
            if item in v.ordered_ids:
                self._fail_refresh(f"destroyed-in-view:{item}")
        # Updated IDs are fetched by the caller; created IDs may enter the
        # query, therefore they still force query re-coordination.
        relevant = (set(delta.updated) | set(delta.created)) & set(v.ordered_ids)
        v.pending_work.update(f"get:{item}" for item in relevant if item not in destroyed)
        v.email_state = delta.new_state
        if delta.has_more:
            v.pending_work.add(f"changes:{delta.new_state}")
        else:
            v.pending_work.discard(f"changes:{delta.old_state}")
            v.pending_work.discard(f"changes:{delta.new_state}")
        # Any observed change after a query operation requires query
        # re-coordination, even if IDs are outside the current prefix.
        if delta.created or delta.updated or delta.destroyed:
            v.pending_work.add("query-recheck")
        self._recompute_pending()
        return True

    def apply_query_changes(self, delta: QueryDelta, *, request_generation: int) -> bool:
        v = self.view
        if request_generation != v.generation:
            return False
        if not delta.can_calculate_changes:
            self._fail_refresh("query-cannotCalculateChanges")
            return True
        if delta.too_many_changes:
            self._fail_refresh("query-tooManyChanges")
            return True
        if delta.old_state != v.query_state:
            self._fail_refresh("query-state-context")
            return True
        if delta.total < 0:
            self._fail_protocol("negative-total")
            return False
        current = [item for item in v.ordered_ids if item not in set(delta.removed)]
        if len(set(current)) != len(current):
            self._fail_protocol("duplicate-local-id")
            return False
        # RFC added.index is interpreted against the result after removals.
        # Sorting by index makes application deterministic even if the wire
        # response lists additions in a different order.
        for addition in sorted(delta.added, key=lambda x: (x.index, x.id)):
            if addition.id in current:
                # remove+add represents a move and must not duplicate an ID.
                current.remove(addition.id)
            if addition.index < 0 or addition.index > len(current):
                self._fail_protocol("added-index-out-of-range")
                return False
            current.insert(addition.index, addition.id)
        v.ordered_ids = current[: min(v.prefix_limit, delta.total)]
        v.total = delta.total
        v.query_state = delta.new_state
        # Existing objects remain useful only for IDs that survived.
        v.objects = {item: obj for item, obj in v.objects.items() if item in v.ordered_ids}
        if delta.removed or delta.added:
            v.pending_work.add("query-recheck")
        self._recompute_pending()
        return True

    def fill_gap(
        self,
        ids: Sequence[str],
        *,
        position: int,
        total: int,
        query_state: str,
        request_generation: int,
    ) -> bool:
        """Append one same-query-state page to the known contiguous prefix."""

        v = self.view
        if request_generation != v.generation:
            return False
        if query_state != v.query_state:
            self._fail_refresh("mixed-query-state-gap")
            return True
        if position != len(v.ordered_ids):
            self._fail_protocol("gap-position-not-contiguous")
            return False
        if total < 0 or len(ids) + position > total:
            self._fail_protocol("gap-page-exceeds-total")
            return False
        if len(set(ids)) != len(ids) or set(ids) & set(v.ordered_ids):
            self._fail_protocol("gap-duplicate-id")
            return False
        v.ordered_ids.extend(ids)
        v.ordered_ids = v.ordered_ids[: min(v.prefix_limit, total)]
        v.total = total
        self._recompute_pending()
        return True

    def commit_ready(self) -> dict[str, Any]:
        if self.view.status != Status.READY:
            raise OracleFailure(f"cannot commit {self.view.status.value}: {self.view.pending_work}")
        return self.view.checkpoint()


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise OracleFailure(message)


def _base(*, limit: int = 3, ids: Sequence[str] = ("a", "b", "c"), total: int = 3) -> SyncOracle:
    scope = Scope("https://mail.example", "a1")
    query = QueryKey(scope, "inbox")
    objects = {item: Email(item, subject=f"{item}-subject") for item in ids}
    return SyncOracle.initial(
        scope=scope,
        query=query,
        prefix_limit=limit,
        ids=ids,
        total=total,
        query_state="q0",
        email_state="e0",
        objects=objects,
    )


def scenario_initial_get_order() -> None:
    """Initial object order is mapped by ID, not response list order."""
    oracle = SyncOracle.initial(
        scope=Scope("svc", "a1"),
        query=QueryKey(Scope("svc", "a1"), "inbox"),
        prefix_limit=3,
        ids=("a", "b", "c"),
        total=3,
        query_state="q0",
        email_state="e0",
        objects={
            "c": Email("c", subject="C"),
            "a": Email("a", subject="A"),
            "b": Email("b", subject="B"),
        },
    )
    _check(oracle.view.status is Status.READY, "initial reordered get should be Ready")
    _check(oracle.view.ordered_ids == ["a", "b", "c"], "query order was changed by get order")
    _check(oracle.view.objects["a"].subject == "A", "objects were not keyed by ID")


def scenario_attribute_update_without_query_delta() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    # queryState is deliberately unchanged; Email state has advanced.
    oracle.apply_email_changes(EmailDelta("e0", "e1", updated=("a",)), request_generation=ticket)
    _check(oracle.view.status is Status.PENDING, "updated object must be pending until get")
    oracle.accept_get({"a": Email("a", subject="new", keywords=("$seen",))}, request_generation=ticket)
    # The change itself still requires a query recheck; a list that happened
    # to keep the same ordering must not be declared complete prematurely.
    _check("query-recheck" in oracle.view.pending_work, "Email change skipped query recheck")
    oracle.view.pending_work.discard("query-recheck")  # caller accepted recheck result
    oracle._recompute_pending()
    _check(oracle.view.status is Status.READY, "attribute-only update did not settle")
    _check(oracle.view.objects["a"].subject == "new", "updated attributes were not applied")


def scenario_remove_middle_and_fill_gap() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    ok = oracle.apply_query_changes(
        QueryDelta("q0", "q1", removed=("b",), total=3), request_generation=ticket
    )
    _check(ok and oracle.view.ordered_ids == ["a", "c"], "middle removal was applied incorrectly")
    _check(oracle.view.status is Status.PENDING, "missing tail must not be Ready")
    oracle.fill_gap(("d",), position=2, total=3, query_state="q1", request_generation=ticket)
    oracle.accept_get({"d": Email("d", subject="D")}, request_generation=ticket)
    oracle.view.pending_work.discard("query-recheck")
    oracle._recompute_pending()
    _check(oracle.view.ordered_ids == ["a", "c", "d"], "gap did not restore contiguous prefix")
    _check(oracle.view.status is Status.READY, "same-state gap fill should be committable")


def scenario_mixed_state_gap_rejected() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.apply_query_changes(QueryDelta("q0", "q1", removed=("b",), total=3), request_generation=ticket)
    oracle.fill_gap(("d",), position=2, total=3, query_state="q2", request_generation=ticket)
    _check(oracle.view.status is Status.NEEDS_REFRESH, "mixed query states were concatenated")
    _check(any("mixed-query-state-gap" in p for p in oracle.view.pending_work), "missing mixed-state reason")


def scenario_query_history_invalidated() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.apply_query_changes(
        QueryDelta("q0", "ignored", can_calculate_changes=False), request_generation=ticket
    )
    _check(oracle.view.status is Status.NEEDS_REFRESH, "query history invalidation not surfaced")
    _check(oracle.view.query_state == "q0", "invalid query token was advanced")


def scenario_email_history_invalidated() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.apply_email_changes(
        EmailDelta("e0", "ignored", can_calculate_changes=False), request_generation=ticket
    )
    _check(oracle.view.status is Status.NEEDS_REFRESH, "Email history invalidation not surfaced")
    _check(oracle.view.email_state == "e0", "invalid Email token was advanced")


def scenario_email_changes_pagination_and_opaque_tokens() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    # The second token is lexically smaller on purpose: state tokens are opaque.
    oracle.apply_email_changes(EmailDelta("e0", "z9", updated=("a",), has_more=True), request_generation=ticket)
    _check(oracle.view.email_state == "z9", "first changes page not accepted")
    _check(oracle.view.status is Status.PENDING, "hasMoreChanges page became Ready")
    oracle.apply_email_changes(EmailDelta("z9", "a1", updated=("a",)), request_generation=ticket)
    _check(oracle.view.email_state == "a1", "opaque token was compared by magnitude")


def scenario_get_state_gap_requires_changes() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.accept_get(
        {"a": Email("a", subject="observed")},
        request_generation=ticket,
        observed_state="e1",
    )
    _check(oracle.view.email_state == "e0", "get observation jumped the Email progress token")
    _check("changes:e0" in oracle.view.pending_work, "get state gap did not schedule Email/changes")
    _check(oracle.view.status is Status.PENDING, "get state gap was reported as Ready")


def scenario_invalid_added_index_rejected() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.apply_query_changes(
        QueryDelta("q0", "q1", added=(Added("x", 99),), total=4), request_generation=ticket
    )
    _check(oracle.view.status is Status.PROTOCOL_FAILURE, "out-of-range added.index was clamped")
    _check(oracle.view.query_state == "q0", "invalid query delta advanced queryState")


def scenario_query_too_many_changes_requires_requery() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.apply_query_changes(
        QueryDelta("q0", "ignored", total=3, too_many_changes=True), request_generation=ticket
    )
    _check(oracle.view.status is Status.NEEDS_REFRESH, "tooManyChanges did not requery")
    _check(oracle.view.query_state == "q0", "tooManyChanges advanced the invalid queryState")


def scenario_not_found_is_not_empty_success() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.accept_get({}, request_generation=ticket, not_found=("b",))
    _check(oracle.view.status is Status.NEEDS_REFRESH, "notFound was turned into a successful deletion")
    _check(oracle.view.ordered_ids == ["a", "b", "c"], "notFound fabricated a new query order")


def scenario_old_generation_cannot_overwrite() -> None:
    oracle = _base()
    old_ticket = oracle.issue_ticket()
    new_ticket = oracle.issue_ticket()
    applied = oracle.accept_get(
        {"a": Email("a", subject="late-old")}, request_generation=old_ticket
    )
    _check(not applied, "late old response was applied")
    oracle.accept_get({"a": Email("a", subject="new")}, request_generation=new_ticket)
    _check(oracle.view.objects["a"].subject == "new", "current response did not apply")


def scenario_identity_bound_tokens() -> None:
    first = _base()
    other_scope = Scope("https://mail.example", "a2")
    other_query = QueryKey(other_scope, "inbox")
    second = SyncOracle.initial(
        scope=other_scope,
        query=other_query,
        prefix_limit=3,
        ids=("a", "b", "c"),
        total=3,
        query_state="q0",
        email_state="e0",
        objects={item: Email(item) for item in ("a", "b", "c")},
    )
    ticket = second.issue_ticket()
    second.apply_query_changes(QueryDelta("other-q0", "q1", total=3), request_generation=ticket)
    _check(second.view.status is Status.NEEDS_REFRESH, "token from another query context was reused")
    _check(first.view.status is Status.READY, "unrelated account was mutated")


def scenario_budget_pending_is_resumable() -> None:
    oracle = _base()
    ticket = oracle.issue_ticket()
    oracle.apply_email_changes(EmailDelta("e0", "e1", updated=("a",), has_more=True), request_generation=ticket)
    _check(oracle.view.status is Status.PENDING, "budget/continuation state was not retained")
    checkpoint = oracle.view.checkpoint()
    _check(checkpoint["email_progress"] == "e1", "pending checkpoint lost progress")
    _check("changes:e1" in checkpoint["pending_work"], "pending checkpoint lost continuation marker")


def scenario_response_container_preserves_duplicate_call_ids() -> None:
    response = parse_method_responses(
        json.dumps(
            [
                ["Email/query", {"ids": ["a"]}, "x"],
                ["error", {"type": "invalidArguments"}, "x"],
            ]
        )
    )
    _check([item[2] for item in response] == ["x", "x"], "duplicate call IDs were collapsed")
    _check(response[0][0] == "Email/query" and response[1][0] == "error", "response order changed")


def scenario_malformed_response_and_invalid_reference() -> None:
    for raw in ("{}", "[1]", "[[\"Email/query\", {}]]", "[[\"Email/query\", null, \"c\"]]"):
        try:
            parse_method_responses(raw)
        except ValueError:
            pass
        else:
            raise OracleFailure(f"malformed response accepted: {raw}")


def scenario_deterministic_delta_fuzz() -> None:
    """Compare incremental remove/add application with a full-list oracle.

    This catches index-order and remove+add move bugs without trusting the
    implementation under test to generate its own expected answer.
    """

    rng = random.Random(8621)
    for trial in range(250):
        n = rng.randint(0, 8)
        initial = [f"m{i}" for i in range(n)]
        current = list(initial)
        removed = tuple(rng.sample(current, rng.randint(0, len(current)))) if current else ()
        after_remove = [item for item in current if item not in set(removed)]
        incoming = [f"n{trial}_{i}" for i in range(rng.randint(0, 5))]
        additions: list[Added] = []
        # Generate valid insertion positions against the evolving list.  The
        # wire contract applies all additions by ascending index, so the
        # independently computed expected list must use that same order even
        # when the generated response lists additions differently.
        expected = list(after_remove)
        for item in incoming:
            index = rng.randint(0, len(expected))
            additions.append(Added(item, index))
            expected.insert(index, item)
        expected = list(after_remove)
        for addition in sorted(additions, key=lambda x: (x.index, x.id)):
            expected.insert(addition.index, addition.id)
        oracle = SyncOracle.initial(
            scope=Scope("svc", "a1"),
            query=QueryKey(Scope("svc", "a1"), "box"),
            prefix_limit=max(1, len(initial), len(expected) + 2),
            ids=initial,
            total=len(initial),
            query_state="q0",
            email_state="e0",
            objects={item: Email(item) for item in initial},
        )
        ticket = oracle.issue_ticket()
        total = len(expected)
        oracle.apply_query_changes(
            QueryDelta("q0", "q1", removed=removed, added=tuple(additions), total=total),
            request_generation=ticket,
        )
        _check(
            oracle.view.ordered_ids == expected,
            f"fuzz trial {trial}: expected {expected}, got {oracle.view.ordered_ids}",
        )


def parse_method_responses(raw: str) -> list[tuple[str, dict[str, Any], str]]:
    """Parse the JMAP method response container without collapsing call IDs."""

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("malformed JSON") from exc
    if not isinstance(value, list):
        raise ValueError("methodResponses must be an array")
    result: list[tuple[str, dict[str, Any], str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError("each method response must be a three-element array")
        name, args, call_id = item
        if not isinstance(name, str) or not isinstance(args, dict) or not isinstance(call_id, str):
            raise ValueError("invalid method response tuple")
        result.append((name, args, call_id))
    return result


SCENARIOS = {
    "initial_get_order": scenario_initial_get_order,
    "attribute_update_without_query_delta": scenario_attribute_update_without_query_delta,
    "remove_middle_and_fill_gap": scenario_remove_middle_and_fill_gap,
    "mixed_state_gap_rejected": scenario_mixed_state_gap_rejected,
    "query_history_invalidated": scenario_query_history_invalidated,
    "email_history_invalidated": scenario_email_history_invalidated,
    "email_changes_pagination_and_opaque_tokens": scenario_email_changes_pagination_and_opaque_tokens,
    "get_state_gap_requires_changes": scenario_get_state_gap_requires_changes,
    "invalid_added_index_rejected": scenario_invalid_added_index_rejected,
    "query_too_many_changes_requires_requery": scenario_query_too_many_changes_requires_requery,
    "not_found_is_not_empty_success": scenario_not_found_is_not_empty_success,
    "old_generation_cannot_overwrite": scenario_old_generation_cannot_overwrite,
    "identity_bound_tokens": scenario_identity_bound_tokens,
    "budget_pending_is_resumable": scenario_budget_pending_is_resumable,
    "response_container_preserves_duplicate_call_ids": scenario_response_container_preserves_duplicate_call_ids,
    "malformed_response_and_invalid_reference": scenario_malformed_response_and_invalid_reference,
    "deterministic_delta_fuzz": scenario_deterministic_delta_fuzz,
}


STRUCTURE = {
    "src/sync": "public synchronization state machine",
    "src/jmap": "four-method JMAP envelope model",
    "src/email": "bounded Email view specification",
    "tests": "independent oracle and vectors",
    "README.md": "scope and non-goals",
    # The implementation uses these concrete filenames; they jointly cover
    # the RFC support and budget/limits sections of the planning document.
    "docs/support-matrix.md": "support matrix with RFC boundaries",
    "docs/recovery-and-budget.md": "resource and completeness limits",
}


def static_structure(root: Path, strict: bool) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    warnings: list[str] = []
    for relative, description in STRUCTURE.items():
        if not (root / relative).exists():
            missing.append(f"{relative} ({description})")
    # The final product is deliberately a sync kernel.  These broad modules
    # are warnings for review, not hard failures, because an example adapter
    # may legitimately live outside src/.
    for forbidden in ("src/http", "src/transport", "src/sse", "src/smtp", "src/imap", "src/pop3", "src/mime"):
        if (root / forbidden).exists():
            warnings.append(f"broad out-of-scope module present: {forbidden}")
    if strict and missing:
        raise OracleFailure("missing required structure: " + "; ".join(missing))
    return missing, warnings


def run(strict_structure: bool = False, selected: Sequence[str] | None = None) -> int:
    names = list(selected or SCENARIOS)
    unknown = sorted(set(names) - set(SCENARIOS))
    if unknown:
        print("unknown scenario(s): " + ", ".join(unknown), file=sys.stderr)
        return 2
    passed = 0
    failed = 0
    for name in names:
        try:
            SCENARIOS[name]()
        except Exception as exc:  # keep all failures visible in one run
            failed += 1
            print(f"FAIL {name}: {exc}")
        else:
            passed += 1
            print(f"PASS {name}")
    root = Path(__file__).resolve().parents[1]
    missing, warnings = static_structure(root, strict_structure)
    for item in missing:
        print(f"WARN structure missing: {item}")
    for item in warnings:
        print(f"WARN {item}")
    print(json.dumps({"oracle_pass": passed, "oracle_fail": failed, "structure_missing": len(missing), "warnings": len(warnings)}, ensure_ascii=False))
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-structure", action="store_true", help="fail when required project paths are absent")
    parser.add_argument("--scenario", action="append", choices=sorted(SCENARIOS), help="run only selected scenario(s)")
    args = parser.parse_args(argv)
    return run(strict_structure=args.strict_structure, selected=args.scenario)


if __name__ == "__main__":
    raise SystemExit(main())

