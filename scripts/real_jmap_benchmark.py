#!/usr/bin/env python3
"""Measure MoonJMAP's fixed JMAP calls against an explicitly supplied server.

This is deliberately a small, dependency-free *live* harness.  It does not
invent a server, replay a fixture, or use the JSON size of a local model as a
wire measurement.  A run is eligible for ``performance_claim=true`` only when
the session request and every requested JMAP call received an HTTP response
from the configured endpoint.  The output contains timings, wire byte counts,
method counters, and redacted summaries; credentials, raw IDs, message
content, and response bodies are never written.

Required configuration is supplied by command-line options or environment:

    JMAP_SESSION_URL       Session URL (normally ``.../jmap/session``)
    JMAP_ACCESS_TOKEN      Bearer token; read but never emitted
    JMAP_ACCOUNT_ID        Account id (otherwise the personal account in the
                           session response is selected)
    JMAP_MAILBOX_ID        Mailbox used by MoonJMAP's fixed ``inMailbox``
                           filter

Example (the command intentionally requires a real account and token):

    JMAP_ACCESS_TOKEN=... JMAP_ACCOUNT_ID=u123 JMAP_MAILBOX_ID=inbox \
      python3 scripts/real_jmap_benchmark.py \
      --session-url https://api.example.test/jmap/session \
      --iterations 5 --output outputs/real-benchmark/run.json

An unauthenticated or missing configuration run produces a ``blocked`` report
when ``--output`` is supplied and exits non-zero.  Such a report is evidence of
the external prerequisite, never a performance result.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
MAIL_CAPABILITY = "urn:ietf:params:jmap:mail"
CORE_CAPABILITY = "urn:ietf:params:jmap:core"
FIXED_PROPERTIES = [
    "id",
    "threadId",
    "mailboxIds",
    "keywords",
    "receivedAt",
    "subject",
    "from",
    "preview",
]
SORT = [{"property": "receivedAt", "isAscending": False}]
REDACTION_VERSION = 1


def digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _hash_string(value: Any) -> str | None:
    return None if value is None else digest(str(value))


def _hash_ids(values: Iterable[Any]) -> str:
    return digest([str(value) for value in values])


def _safe_endpoint(url: str) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    structural = {"", ".well-known", "jmap", "api", "session", "v1", "v2"}
    safe_path = "/".join(
        segment
        if segment in structural or segment.startswith("{")
        else digest(segment)
        for segment in parsed.path.split("/")
    )
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port,
        "path": safe_path or "/",
    }


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _redact_scalar(value: Any) -> Any:
    """Redact IDs, states, addresses, and opaque strings without leaking them."""

    if isinstance(value, str):
        return _hash_string(value)
    if isinstance(value, list):
        return [_redact_scalar(x) for x in value]
    if isinstance(value, dict):
        return {str(key): _redact_scalar(item) for key, item in value.items()}
    return value


def _response_summary(method: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Keep counts and hashes needed for audit, never raw JMAP values."""

    summary: dict[str, Any] = {
        "method": method,
        "account_id_hash": _hash_string(arguments.get("accountId")),
    }
    if method == "Email/query":
        ids = arguments.get("ids", [])
        if not isinstance(ids, list):
            ids = []
        summary.update(
            {
                "query_state_hash": _hash_string(arguments.get("queryState")),
                "ids_count": len(ids),
                "ids_hash": _hash_ids(ids),
                "position": arguments.get("position"),
                "total": arguments.get("total"),
                "can_calculate_changes": arguments.get("canCalculateChanges"),
            }
        )
    elif method == "Email/queryChanges":
        removed = arguments.get("removed", [])
        added = arguments.get("added", [])
        if not isinstance(removed, list):
            removed = []
        if not isinstance(added, list):
            added = []
        added_ids = [item.get("id") for item in added if isinstance(item, dict)]
        summary.update(
            {
                "old_query_state_hash": _hash_string(arguments.get("oldQueryState")),
                "new_query_state_hash": _hash_string(arguments.get("newQueryState")),
                "removed_count": len(removed),
                "removed_ids_hash": _hash_ids(removed),
                "added_count": len(added_ids),
                "added_ids_hash": _hash_ids(added_ids),
                "total": arguments.get("total"),
            }
        )
    elif method == "Email/get":
        objects = arguments.get("list", [])
        not_found = arguments.get("notFound", [])
        if not isinstance(objects, list):
            objects = []
        if not isinstance(not_found, list):
            not_found = []
        object_ids = [item.get("id") for item in objects if isinstance(item, dict)]
        summary.update(
            {
                "email_state_hash": _hash_string(arguments.get("state")),
                "objects_count": len(object_ids),
                "object_ids_hash": _hash_ids(object_ids),
                "not_found_count": len(not_found),
                "not_found_ids_hash": _hash_ids(not_found),
                "properties": list(arguments.get("list", [{}])[0].keys()) if objects else [],
            }
        )
    elif method == "Email/changes":
        created = arguments.get("created", [])
        updated = arguments.get("updated", [])
        destroyed = arguments.get("destroyed", [])
        summary.update(
            {
                "old_state_hash": _hash_string(arguments.get("oldState")),
                "new_state_hash": _hash_string(arguments.get("newState")),
                "created_count": len(created) if isinstance(created, list) else 0,
                "updated_count": len(updated) if isinstance(updated, list) else 0,
                "destroyed_count": len(destroyed) if isinstance(destroyed, list) else 0,
                "has_more_changes": arguments.get("hasMoreChanges"),
                "created_ids_hash": _hash_ids(created if isinstance(created, list) else []),
                "updated_ids_hash": _hash_ids(updated if isinstance(updated, list) else []),
                "destroyed_ids_hash": _hash_ids(destroyed if isinstance(destroyed, list) else []),
            }
        )
    return summary


@dataclass
class HttpObservation:
    kind: str
    method: str
    url: dict[str, Any]
    status: int | None
    elapsed_ms: float | None
    request_bytes: int
    response_bytes: int | None
    request_hash: str
    response_hash: str | None
    error: str | None = None
    response_summary: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "request_bytes": self.request_bytes,
            "response_bytes": self.response_bytes,
            "request_sha256": self.request_hash,
            "response_sha256": self.response_hash,
            "error": self.error,
            "response": self.response_summary,
        }


@dataclass
class LiveRun:
    session_url: str
    api_url: str | None
    access_token_present: bool
    account_id: str | None
    mailbox_id: str | None
    iterations: int
    prefix_limit: int
    max_objects: int
    timeout: float
    measure_prefix_fill: bool = True
    auth_scheme: str = "bearer"
    deployment: str = "external-jmap"
    server_product: str | None = None
    server_version: str | None = None
    server_mode: str | None = None
    observations: list[HttpObservation] = field(default_factory=list)
    query_states: list[str] = field(default_factory=list)
    email_states: list[str] = field(default_factory=list)
    query_fill_requests: int = 0
    query_rebuilds: int = 0
    email_rebuilds: int = 0
    failures: list[str] = field(default_factory=list)
    session_capabilities: list[str] = field(default_factory=list)
    session_status: int | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def report(self, *, status: str, reason: str | None = None) -> dict[str, Any]:
        successful = [x for x in self.observations if x.status is not None and 200 <= x.status < 300]
        requests_by_method: dict[str, int] = {}
        for item in self.observations:
            requests_by_method[item.method] = requests_by_method.get(item.method, 0) + 1
        response_sizes = [x.response_bytes for x in successful if x.response_bytes is not None]
        elapsed = [x.elapsed_ms for x in successful if x.elapsed_ms is not None]
        return {
            "schema": "moon-jmap-live-performance-v1",
            "redaction_version": REDACTION_VERSION,
            "status": status,
            "performance_claim": status == "complete" and bool(successful),
            "reason": reason,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": _safe_endpoint(self.session_url),
            "api_endpoint": _safe_endpoint(self.api_url) if self.api_url else None,
            "service": {
                "deployment": self.deployment,
                "product": self.server_product,
                "version": self.server_version,
                "mode": self.server_mode,
            },
            "authentication": {"scheme": self.auth_scheme, "credential_present": self.access_token_present},
            "account_id_hash": _hash_string(self.account_id),
            "mailbox_id_hash": _hash_string(self.mailbox_id),
            "parameters": {
                "iterations": self.iterations,
                "prefix_limit": self.prefix_limit,
                "max_objects_in_get": self.max_objects,
                "timeout_seconds": self.timeout,
                "measure_prefix_fill": self.measure_prefix_fill,
            },
            "session": {
                "status": self.session_status,
                "capabilities": self.session_capabilities,
            },
            "metrics": {
                "requests_attempted": len(self.observations),
                "responses_2xx": len(successful),
                "requests_by_method": requests_by_method,
                "request_bytes": sum(x.request_bytes for x in self.observations),
                "response_bytes": sum(response_sizes) if response_sizes else None,
                "response_bytes_observed": len(response_sizes),
                "rtt_ms": {
                    "count": len(elapsed),
                    "min": min(elapsed) if elapsed else None,
                    "max": max(elapsed) if elapsed else None,
                    "mean": sum(elapsed) / len(elapsed) if elapsed else None,
                    "p50": _percentile(elapsed, 0.50),
                    "p95": _percentile(elapsed, 0.95),
                },
                "objects_received": sum(
                    int((x.response_summary or {}).get("objects_count", 0))
                    for x in successful
                    if x.method == "Email/get"
                ),
                "query_removed": sum(
                    int((x.response_summary or {}).get("removed_count", 0))
                    for x in successful
                    if x.method == "Email/queryChanges"
                ),
                "query_added": sum(
                    int((x.response_summary or {}).get("added_count", 0))
                    for x in successful
                    if x.method == "Email/queryChanges"
                ),
                "query_fill_requests": self.query_fill_requests,
                "query_rebuilds": self.query_rebuilds,
                "email_rebuilds": self.email_rebuilds,
            },
            "state_frontiers": {
                "query_state_hashes": [_hash_string(x) for x in self.query_states],
                "email_state_hashes": [_hash_string(x) for x in self.email_states],
            },
            "failures": list(self.failures),
            "observations": [x.to_json() for x in self.observations],
        }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = max(0, min(len(values) - 1, round((len(values) - 1) * fraction)))
    return values[index]


class JmapHttp:
    def __init__(
        self,
        *,
        token: str | None,
        basic_username: str | None = None,
        basic_password: str | None = None,
        timeout: float,
        allow_http: bool = False,
    ) -> None:
        self.token = token
        self.basic_username = basic_username
        self.basic_password = basic_password
        self.timeout = timeout
        self.allow_http = allow_http

    def _request(self, url: str, payload: Any | None, *, method: str, kind: str) -> tuple[HttpObservation, Any | None]:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"https", "http"}:
            raise ValueError("JMAP URL must use https (or --allow-http for a local test server)")
        if parsed.scheme == "http" and not self.allow_http:
            raise ValueError("refusing plaintext HTTP; pass --allow-http only for an explicitly local test")
        body = b"" if payload is None else _json_bytes(payload)
        headers = {"Accept": "application/json", "User-Agent": "MoonJMAP-live-benchmark/1"}
        if payload is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        elif self.basic_username is not None and self.basic_password is not None:
            encoded = base64.b64encode(
                (self.basic_username + ":" + self.basic_password).encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = "Basic " + encoded
        request = urllib.request.Request(url, data=body if payload is not None else None, headers=headers, method=method)
        started = time.perf_counter_ns()
        status: int | None = None
        raw: bytes | None = None
        error: str | None = None
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=ssl.create_default_context()) as response:
                status = int(response.status)
                raw = response.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            error = f"HTTP {status}"
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            error = type(exc).__name__ + ": " + str(exc)[:240]
        elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
        parsed_body: Any | None = None
        if raw:
            try:
                parsed_body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                error = error or ("invalid JSON response: " + str(exc)[:160])
        observation = HttpObservation(
            kind=kind,
            method=method if kind == "session" else _method_from_payload(payload),
            url=_safe_endpoint(url),
            status=status,
            elapsed_ms=elapsed_ms,
            request_bytes=len(body),
            response_bytes=len(raw) if raw is not None else None,
            request_hash=digest(payload if payload is not None else {"method": method, "url": _safe_endpoint(url)}),
            response_hash=hashlib.sha256(raw).hexdigest() if raw is not None else None,
            error=error,
        )
        if parsed_body is not None and kind == "jmap" and isinstance(parsed_body, dict):
            rows = parsed_body.get("methodResponses", [])
            if isinstance(rows, list):
                # The harness sends one method per request, so one summary is
                # enough; retain an error envelope as a summary too.
                if rows and isinstance(rows[0], list) and len(rows[0]) >= 2 and isinstance(rows[0][1], dict):
                    method_name = str(rows[0][0])
                    observation.method = method_name
                    observation.response_summary = _response_summary(method_name, rows[0][1])
        return observation, parsed_body


def _method_from_payload(payload: Any) -> str:
    try:
        rows = payload.get("methodCalls", [])
        if rows and isinstance(rows[0], list):
            return str(rows[0][0])
    except Exception:
        pass
    return "unknown"


def _session_info(value: Any) -> tuple[str, list[str], list[str]]:
    session = _json_object(value, "session response")
    api_url = _nonempty_string(session.get("apiUrl"), "session.apiUrl")
    capabilities_raw = session.get("capabilities", {})
    capabilities = sorted(str(x) for x in capabilities_raw) if isinstance(capabilities_raw, dict) else []
    accounts = session.get("accounts", {})
    account_ids: list[str] = []
    if isinstance(accounts, dict):
        account_ids = [str(x) for x in accounts]
    return api_url, capabilities, account_ids


def _resolve_api_url(raw_api_url: str, session_url: str, account_id: str) -> str:
    """Resolve RFC 8620's absolute/relative API URL and account template."""

    endpoint = urllib.parse.urljoin(session_url, raw_api_url)
    return endpoint.replace("{accountId}", urllib.parse.quote(account_id, safe=""))


def _account_from_session(value: Any) -> str | None:
    accounts = value.get("accounts") if isinstance(value, dict) else None
    if not isinstance(accounts, dict):
        return None
    personal: list[str] = []
    for account_id, account in accounts.items():
        if isinstance(account, dict) and account.get("isPersonal") is True:
            personal.append(str(account_id))
    return sorted(personal or [str(x) for x in accounts])[0] if accounts else None


def _method_payload(method: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {
        "using": [CORE_CAPABILITY, MAIL_CAPABILITY],
        "methodCalls": [[method, args, call_id]],
    }


def _response_arguments(body: Any, expected_method: str) -> dict[str, Any]:
    obj = _json_object(body, "JMAP response")
    rows = obj.get("methodResponses")
    if not isinstance(rows, list) or not rows:
        raise ValueError("JMAP response has no methodResponses")
    row = rows[0]
    if not isinstance(row, list) or len(row) != 3:
        raise ValueError("JMAP method response must have three tuple elements")
    name = _nonempty_string(row[0], "method response name")
    args = _json_object(row[1], "method response arguments")
    if name == "error":
        raise RuntimeError(f"JMAP {expected_method} error type={args.get('type', 'unknown')!r}")
    if name != expected_method:
        raise ValueError(f"expected {expected_method}, got {name}")
    return args


def run_live(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(args.token_env)
    basic_username = os.environ.get(args.basic_username_env) if args.basic_username_env else None
    basic_password = os.environ.get(args.basic_password_env) if args.basic_password_env else None
    if token:
        auth_scheme = "bearer"
    elif basic_username is not None and basic_password is not None:
        auth_scheme = "basic"
    else:
        auth_scheme = "none"
    session_url = args.session_url or os.environ.get("JMAP_SESSION_URL")
    account_id = args.account_id or os.environ.get("JMAP_ACCOUNT_ID")
    mailbox_id = args.mailbox_id or os.environ.get("JMAP_MAILBOX_ID")
    if not session_url:
        raise RuntimeError("missing --session-url or JMAP_SESSION_URL")
    run = LiveRun(
        session_url=session_url,
        api_url=args.api_url,
        access_token_present=bool(token or (basic_username is not None and basic_password is not None)),
        account_id=account_id,
        mailbox_id=mailbox_id,
        iterations=args.iterations,
        prefix_limit=args.prefix_limit,
        max_objects=args.max_objects,
        timeout=args.timeout,
        measure_prefix_fill=not args.disable_prefix_fill,
        auth_scheme=auth_scheme,
        deployment=args.deployment,
        server_product=args.server_product,
        server_version=args.server_version,
        server_mode=args.server_mode,
    )
    client = JmapHttp(
        token=token,
        basic_username=basic_username if not token else None,
        basic_password=basic_password if not token else None,
        timeout=args.timeout,
        allow_http=args.allow_http,
    )
    session_obs, session_body = client._request(session_url, None, method="GET", kind="session")
    run.observations.append(session_obs)
    run.session_status = session_obs.status
    if session_obs.status is None or not 200 <= session_obs.status < 300:
        reason = "session request failed; supply a real JMAP session URL and valid token"
        run.failures.append(reason)
        return run.report(status="blocked", reason=reason)
    try:
        api_url, capabilities, account_ids = _session_info(session_body)
    except Exception as exc:
        reason = "invalid session response: " + str(exc)
        run.failures.append(reason)
        return run.report(status="blocked", reason=reason)
    run.api_url = args.api_url or api_url
    run.session_capabilities = capabilities
    if not run.access_token_present:
        reason = "session was reachable but no bearer or basic credential was supplied for JMAP API calls"
        run.failures.append(reason)
        return run.report(status="blocked", reason=reason)
    if MAIL_CAPABILITY not in capabilities:
        reason = "session does not advertise the JMAP Mail capability"
        run.failures.append(reason)
        return run.report(status="blocked", reason=reason)
    if not run.account_id:
        run.account_id = _account_from_session(session_body)
    if not run.account_id:
        reason = "no account selected; pass --account-id or JMAP_ACCOUNT_ID"
        run.failures.append(reason)
        return run.report(status="blocked", reason=reason)
    if not run.mailbox_id:
        reason = "no mailbox selected; pass --mailbox-id or JMAP_MAILBOX_ID"
        run.failures.append(reason)
        return run.report(status="blocked", reason=reason)
    run.api_url = _resolve_api_url(run.api_url, session_url, run.account_id)

    filter_value = {"inMailbox": run.mailbox_id}
    previous_query_state: str | None = None
    previous_email_state: str | None = None
    for iteration in range(run.iterations):
        query_args = {
            "accountId": run.account_id,
            "filter": filter_value,
            "sort": SORT,
            "collapseThreads": False,
            "position": 0,
            "limit": run.prefix_limit,
            "calculateTotal": True,
        }
        query_payload = _method_payload("Email/query", query_args, f"q{iteration}")
        obs, body = client._request(run.api_url, query_payload, method="POST", kind="jmap")
        run.observations.append(obs)
        if obs.status is None or not 200 <= obs.status < 300:
            run.failures.append(f"iteration {iteration}: Email/query failed")
            continue
        try:
            query = _response_arguments(body, "Email/query")
            query_state = _nonempty_string(query.get("queryState"), "Email/query.queryState")
            ids = query.get("ids")
            if not isinstance(ids, list):
                raise ValueError("Email/query.ids must be an array")
            run.query_states.append(query_state)
        except Exception as exc:
            run.failures.append(f"iteration {iteration}: {exc}")
            continue
        # A real server can return a shorter page than the requested prefix.
        # Measure one continuation page when ``total`` proves that the prefix
        # is incomplete.  The second response must carry the same queryState;
        # a changed state is recorded as a rebuild boundary, never silently
        # stitched into the first page.
        total = query.get("total")
        if run.measure_prefix_fill and isinstance(total, int) and total > len(ids):
            fill_args = {
                "accountId": run.account_id,
                "filter": filter_value,
                "sort": SORT,
                "collapseThreads": False,
                "position": len(ids),
                "limit": run.prefix_limit,
                "calculateTotal": True,
            }
            fill_payload = _method_payload("Email/query", fill_args, f"qfill{iteration}")
            fill_obs, fill_body = client._request(run.api_url, fill_payload, method="POST", kind="jmap")
            run.observations.append(fill_obs)
            run.query_fill_requests += 1
            if fill_obs.status is not None and 200 <= fill_obs.status < 300:
                try:
                    fill = _response_arguments(fill_body, "Email/query")
                    fill_state = _nonempty_string(fill.get("queryState"), "Email/query fill.queryState")
                    run.query_states.append(fill_state)
                    if fill_state != query_state:
                        run.query_rebuilds += 1
                except Exception as exc:
                    run.failures.append(f"iteration {iteration}: prefix fill: {exc}")
            else:
                run.failures.append(f"iteration {iteration}: prefix fill failed")
        if previous_query_state is not None:
            qc_args = {
                "accountId": run.account_id,
                "filter": filter_value,
                "sort": SORT,
                "collapseThreads": False,
                "sinceQueryState": previous_query_state,
                "maxChanges": max(1, run.prefix_limit),
            }
            qc_payload = _method_payload("Email/queryChanges", qc_args, f"qc{iteration}")
            qc_obs, qc_body = client._request(run.api_url, qc_payload, method="POST", kind="jmap")
            run.observations.append(qc_obs)
            if qc_obs.status is not None and 200 <= qc_obs.status < 300:
                try:
                    qc = _response_arguments(qc_body, "Email/queryChanges")
                    new_state = _nonempty_string(qc.get("newQueryState"), "Email/queryChanges.newQueryState")
                    run.query_states.append(new_state)
                except Exception as exc:
                    run.failures.append(f"iteration {iteration}: {exc}")
            elif qc_obs.status == 400:
                run.query_rebuilds += 1
        get_chunks = [ids[start : start + max(1, run.max_objects)] for start in range(0, len(ids), max(1, run.max_objects))]
        # Empty Email/get is an intentional baseline: it obtains the account's
        # Email state on a real empty mailbox, so the subsequent Email/changes
        # measurement is still a four-method JMAP run rather than an omitted
        # method hidden by a zero-object dataset.
        if not get_chunks:
            get_chunks = [[]]
        for start, chunk in enumerate(get_chunks):
            get_args = {
                "accountId": run.account_id,
                "ids": chunk,
                "properties": FIXED_PROPERTIES,
            }
            get_payload = _method_payload("Email/get", get_args, f"g{iteration}-{start}")
            get_obs, get_body = client._request(run.api_url, get_payload, method="POST", kind="jmap")
            run.observations.append(get_obs)
            if get_obs.status is not None and 200 <= get_obs.status < 300:
                try:
                    get = _response_arguments(get_body, "Email/get")
                    state = _nonempty_string(get.get("state"), "Email/get.state")
                    run.email_states.append(state)
                    previous_email_state = state
                except Exception as exc:
                    run.failures.append(f"iteration {iteration}: {exc}")
        if previous_email_state is not None:
            changes_args = {
                "accountId": run.account_id,
                "sinceState": previous_email_state,
                "maxChanges": max(1, run.prefix_limit),
            }
            changes_payload = _method_payload("Email/changes", changes_args, f"c{iteration}")
            changes_obs, changes_body = client._request(run.api_url, changes_payload, method="POST", kind="jmap")
            run.observations.append(changes_obs)
            if changes_obs.status == 400:
                run.email_rebuilds += 1
            elif changes_obs.status is not None and 200 <= changes_obs.status < 300:
                try:
                    changes = _response_arguments(changes_body, "Email/changes")
                    state = _nonempty_string(changes.get("newState"), "Email/changes.newState")
                    run.email_states.append(state)
                    previous_email_state = state
                except Exception as exc:
                    run.failures.append(f"iteration {iteration}: {exc}")
        previous_query_state = query_state

    status = "complete" if not run.failures and any(x.status is not None and 200 <= x.status < 300 for x in run.observations) else "partial"
    return run.report(status=status, reason=None if status == "complete" else "one or more live calls failed")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--session-url", help="real JMAP Session URL (or JMAP_SESSION_URL)")
    p.add_argument("--api-url", help="override session.apiUrl")
    p.add_argument("--token-env", default="JMAP_ACCESS_TOKEN", help="environment variable containing bearer token")
    p.add_argument("--basic-username-env", default="JMAP_BASIC_USERNAME", help="environment variable containing Basic auth username")
    p.add_argument("--basic-password-env", default="JMAP_BASIC_PASSWORD", help="environment variable containing Basic auth password")
    p.add_argument("--account-id", help="JMAP account id (or JMAP_ACCOUNT_ID)")
    p.add_argument("--mailbox-id", help="mailbox id for fixed inMailbox filter (or JMAP_MAILBOX_ID)")
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--prefix-limit", type=int, default=50)
    p.add_argument("--max-objects", type=int, default=50)
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--disable-prefix-fill", action="store_true", help="do not issue a continuation Email/query when total exceeds the first page")
    p.add_argument("--deployment", default="external-jmap", help="deployment label stored in the report, e.g. local-real-stalwart")
    p.add_argument("--server-product", help="server product name recorded in the report")
    p.add_argument("--server-version", help="server version recorded in the report")
    p.add_argument("--server-mode", help="server mode recorded in the report, e.g. recovery or normal")
    p.add_argument("--allow-http", action="store_true", help="allow plaintext HTTP only for an explicitly local test server")
    p.add_argument("--output", type=Path, help="write the redacted JSON report")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.iterations <= 0 or args.prefix_limit <= 0 or args.max_objects <= 0 or args.timeout <= 0:
        print("iterations, prefix-limit, max-objects and timeout must be positive", file=sys.stderr)
        return 2
    try:
        report = run_live(args)
    except Exception as exc:
        report = {
            "schema": "moon-jmap-live-performance-v1",
            "redaction_version": REDACTION_VERSION,
            "status": "blocked",
            "performance_claim": False,
            "reason": str(exc),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
