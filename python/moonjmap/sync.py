"""Historical Python compatibility model; not the v0.1 delivery API.

The authoritative implementation is the dependency-free MoonBit package under
``src/sync``.  This module predates the current v0.1 contract and keeps a
small, transport-free helper surface for old local scripts.  It is retained as
a migration reference only: it is not used by the acceptance oracle, is not a
wire adapter, and makes no API or behavioural parity claim with ``src/sync``.
The current acceptance oracle is ``tests/verify.py`` and the current public
contract is documented in ``docs/state-contract.md``.

State tokens in this legacy model are opaque strings: they are only compared
for equality and never parsed or ordered.  Do not use this module as evidence
of v0.1 feature coverage or real-server interoperability.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Mapping, Sequence


class Completeness(str, Enum):
    READY = "Ready"
    PENDING = "Pending"
    NEEDS_REFRESH = "NeedsRefresh"
    UNSUPPORTED = "Unsupported"
    PROTOCOL_FAILURE = "ProtocolFailure"


@dataclass(frozen=True, slots=True)
class AccountScope:
    service_identity: str
    account_id: str


@dataclass(frozen=True, slots=True)
class QueryKey:
    scope: AccountScope
    mailbox_id: str
    unread_only: bool = False
    sort: str = "receivedAt:desc"
    collapse_threads: bool = False

    def __post_init__(self) -> None:
        if not self.scope.service_identity or not self.scope.account_id:
            raise ValueError("account scope must be non-empty")
        if not self.mailbox_id:
            raise ValueError("mailbox id must be non-empty")
        if self.sort != "receivedAt:desc":
            raise ValueError("v0.1 supports receivedAt:desc only")
        if self.collapse_threads:
            raise ValueError("collapseThreads is fixed to false in v0.1")


@dataclass(frozen=True, slots=True)
class Limits:
    prefix_limit: int = 50
    max_calls: int = 8
    max_objects: int = 100
    max_bytes: int = 2_000_000
    max_rounds: int = 4
    max_changes: int = 500

    def __post_init__(self) -> None:
        for name in ("prefix_limit", "max_calls", "max_objects", "max_bytes", "max_rounds", "max_changes"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class EmailRecord:
    id: str
    thread_id: str = ""
    mailbox_ids: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    received_at: str = ""
    subject: str = ""
    sender: str = ""
    preview: str = ""


@dataclass(frozen=True, slots=True)
class Added:
    id: str
    index: int


@dataclass(frozen=True, slots=True)
class EmailView:
    scope: AccountScope
    query: QueryKey
    prefix_limit: int
    ordered_ids: tuple[str, ...] = ()
    total: int = 0
    objects: Mapping[str, EmailRecord] = field(default_factory=dict)
    email_covered_state: str | None = None
    email_observed_state: str | None = None
    query_state: str | None = None
    completeness: Completeness = Completeness.PENDING
    pending_work: tuple[str, ...] = ()
    generation: int = 0

    def __post_init__(self) -> None:
        if self.scope != self.query.scope:
            raise ValueError("query scope does not match view scope")
        if self.prefix_limit < 1:
            raise ValueError("prefix_limit must be positive")
        if len(self.ordered_ids) > self.prefix_limit:
            raise ValueError("ordered prefix exceeds limit")
        if len(set(self.ordered_ids)) != len(self.ordered_ids):
            raise ValueError("ordered prefix contains duplicate ids")
        if self.total < 0:
            raise ValueError("total cannot be negative")

    @property
    def target_length(self) -> int:
        return min(self.prefix_limit, self.total)


@dataclass(frozen=True, slots=True)
class SyncResult:
    status: Completeness
    view: EmailView
    reason: str = ""
    requested_ids: tuple[str, ...] = ()
    stale: bool = False


def begin_refresh(view: EmailView, *, generation: int | None = None) -> EmailView:
    return replace(
        view,
        generation=view.generation + 1 if generation is None else generation,
        completeness=Completeness.PENDING,
        pending_work=("Email/changes", "Email/queryChanges"),
    )


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _ready_if_complete(view: EmailView) -> EmailView:
    needed = view.target_length
    complete = (
        len(view.ordered_ids) == needed
        and all(identifier in view.objects for identifier in view.ordered_ids)
        and view.email_covered_state is not None
        and view.query_state is not None
    )
    return replace(
        view,
        completeness=Completeness.READY if complete else Completeness.PENDING,
        pending_work=() if complete else ("fill-or-get",),
    )


def apply_query_changes(
    view: EmailView,
    *,
    old_state: str,
    new_state: str,
    removed: Sequence[str] = (),
    added: Sequence[Added] = (),
    total: int,
    fill_ids: Sequence[str] = (),
    fill_state: str | None = None,
    has_more_changes: bool = False,
) -> SyncResult:
    """Apply one queryChanges response and an optional same-state prefix fill."""
    if view.query_state != old_state:
        return SyncResult(Completeness.NEEDS_REFRESH, view, "query_state_mismatch")
    if total < 0 or any(item.index < 0 for item in added):
        return SyncResult(Completeness.PROTOCOL_FAILURE, view, "invalid_query_delta")

    removed_set = set(removed)
    ids = [identifier for identifier in view.ordered_ids if identifier not in removed_set]
    for item in sorted(added, key=lambda item: item.index):
        ids = [identifier for identifier in ids if identifier != item.id]
        ids.insert(min(item.index, len(ids)), item.id)
    ids = _dedupe(ids)[: view.prefix_limit]
    target = min(view.prefix_limit, total)

    if len(ids) < target:
        if fill_state != new_state:
            pending = replace(view, ordered_ids=tuple(ids), total=total, query_state=new_state)
            return SyncResult(Completeness.NEEDS_REFRESH, pending, "fill_query_state_mismatch")
        for identifier in fill_ids:
            if identifier not in ids and len(ids) < target:
                ids.append(identifier)
        if len(ids) < target:
            pending = replace(view, ordered_ids=tuple(ids), total=total, query_state=new_state)
            return SyncResult(Completeness.PENDING, pending, "prefix_fill_required", tuple(fill_ids))

    next_view = replace(
        view,
        ordered_ids=tuple(ids[:target]),
        total=total,
        query_state=new_state,
        completeness=Completeness.PENDING,
        pending_work=("追赶 queryChanges",) if has_more_changes else (),
    )
    if has_more_changes:
        return SyncResult(Completeness.PENDING, next_view, "query_changed_during_refresh")
    ready = _ready_if_complete(next_view)
    return SyncResult(ready.completeness, ready, "")


def apply_email_get(
    view: EmailView,
    *,
    state: str,
    records: Mapping[str, EmailRecord],
    not_found: Sequence[str] = (),
    expected_state: str | None = None,
) -> SyncResult:
    """Accept Email/get without silently jumping over Email/changes."""
    if any(identifier in records and records[identifier].id != identifier for identifier in records):
        return SyncResult(Completeness.PROTOCOL_FAILURE, view, "get_id_mismatch")
    if not_found and any(identifier in view.ordered_ids for identifier in not_found):
        next_view = replace(view, email_observed_state=state, completeness=Completeness.NEEDS_REFRESH)
        return SyncResult(Completeness.NEEDS_REFRESH, next_view, "window_object_not_found")
    merged = dict(view.objects)
    merged.update(records)
    observed = replace(view, objects=merged, email_observed_state=state)
    if expected_state is not None and expected_state != state:
        return SyncResult(Completeness.PROTOCOL_FAILURE, observed, "get_expected_state_mismatch")
    if view.email_covered_state is not None and state != view.email_covered_state:
        return SyncResult(Completeness.NEEDS_REFRESH, observed, "email_state_gap")
    ready = _ready_if_complete(observed)
    return SyncResult(ready.completeness, ready, "")
