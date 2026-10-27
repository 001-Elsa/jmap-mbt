"""Read-only HTTP probe for recording real JMAP interoperability evidence.

The MoonJMAP core deliberately has no transport implementation.  This module
is a small, opt-in adapter for a *real* JMAP service: it discovers a JMAP
Session, sends the four fixed mail methods, and writes a redacted evidence
record.  It is intentionally conservative:

* no request is made until :meth:`JmapHttpProbe.get_session` or
  :meth:`JmapHttpProbe.call` is invoked;
* callers may require an explicit ``allow_network`` flag (the CLI does);
* authorization, cookies, message content, addresses, account IDs, object IDs,
  and opaque states never appear in the record in clear text;
* only the fixed MoonJMAP method subset is constructed and decoded.

This is evidence tooling, not a generic JMAP client or an authentication
library.  The returned typed values are the existing ``src/jmap`` wire model,
so an application can feed them into the synchronisation core without adding a
second protocol interpretation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import ssl
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.client import HTTPMessage
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .errors import JmapMethodError, ProtocolFailure
from .methods import (
    EmailChangesRequest,
    EmailGetRequest,
    EmailQueryChangesRequest,
    EmailQueryRequest,
    JmapRequest,
    JmapResponse,
    MethodResponse,
)


class ProbeError(RuntimeError):
    """A transport, session, or probe configuration failure."""


class NetworkDisabled(ProbeError):
    """Raised when the caller did not explicitly permit network access."""


_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|set-cookie|token|secret|password|passwd|api[-_]?key|"
    r"access[-_]?token|refresh[-_]?token|client[-_]?secret|private[-_]?key)",
    re.IGNORECASE,
)
_CONTENT_KEYS = frozenset(
    {
        "body",
        "textbody",
        "htmlbody",
        "attachment",
        "blob",
        "subject",
        "preview",
        "address",
        "email",
        "sender",
        "recipient",
        "from",
        "to",
        "cc",
        "bcc",
        "replyto",
        "name",
    }
)
_URL_KEY = re.compile(r"(?:url|uri|href)$", re.IGNORECASE)
_IDENTIFIER_KEYS = frozenset(
    {
        "id",
        "ids",
        "accountid",
        "accountids",
        "inmailbox",
        "mailboxids",
        "threadid",
        "notfound",
        "created",
        "updated",
        "destroyed",
        "state",
        "oldstate",
        "newstate",
        "sincestate",
        "querystate",
        "oldquerystate",
        "newquerystate",
        "sincequerystate",
    }
)


def _digest(value: Any) -> str:
    """Return a stable, non-reversible marker for a scalar or JSON value."""

    if isinstance(value, (dict, list, tuple)):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        encoded = str(value)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def redact_json(value: Any, *, key: str | None = None, secrets: Sequence[str] = ()) -> Any:
    """Redact sensitive JSON while retaining shape and stable comparisons.

    The function is deliberately independent of the HTTP client so tests and
    record post-processors can use exactly the same policy.  Dynamic object
    identifiers and state tokens are hashed, while content and credentials are
    replaced completely.  Unknown fields are traversed recursively.
    """

    normalized_key = key.replace("-", "").replace("_", "").lower() if key else ""
    if isinstance(value, str) and value and value in secrets:
        return "<redacted>"
    if isinstance(value, str) and key and _URL_KEY.search(key):
        return safe_url(value)
    if key and _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if normalized_key in _CONTENT_KEYS:
        return "<redacted>"
    if normalized_key in _IDENTIFIER_KEYS:
        if isinstance(value, (list, tuple)):
            return [redact_json(item, key="id", secrets=secrets) for item in value]
        if isinstance(value, Mapping):
            return {
                (_digest(str(k)) if normalized_key in {"mailboxids", "accounts", "primaryaccounts"} else str(k)): redact_json(v, key="id", secrets=secrets)
                for k, v in value.items()
            }
        return _digest(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            # JSON object names are strings on the wire.  Keep an unexpected
            # Python key printable without allowing it to leak the value.
            child_key = str(raw_key)
            if normalized_key in {"accounts", "primaryaccounts", "mailboxids"}:
                safe_key = _digest(child_key)
            else:
                safe_key = child_key
            value_key = "accountId" if normalized_key == "primaryaccounts" else child_key
            result[safe_key] = redact_json(item, key=value_key, secrets=secrets)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_json(item, key=key, secrets=secrets) for item in value]
    return value


def safe_url(value: str) -> str:
    """Return a non-routable URL-shaped marker for a URL used in a record.

    The scheme and structural path are retained for troubleshooting, but the
    host is replaced with ``service.invalid`` so a record cannot itself be
    copied into a browser or HTTP client as a service endpoint.
    """

    try:
        parts = urlsplit(value)
    except ValueError:
        return "<invalid-url>"
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "<invalid-url>"
    # Do not retain a routable host or port in an evidence artifact.  The
    # service product/version belongs in the human-filled record metadata.
    netloc = "service.invalid"
    # A JMAP apiUrl is allowed to expand ``{accountId}`` into a path segment.
    # Keep well-known structural segments useful for diagnostics while hashing
    # every other non-empty segment so account IDs and tenant paths cannot leak
    # through the request URL recorded below.
    path_parts = parts.path.split("/")
    if path_parts[:3] == ["", ".well-known", "jmap"]:
        structural_prefix = 3
    elif path_parts[:3] == ["", "jmap", "api"]:
        structural_prefix = 3
    elif path_parts[:2] == ["", "api"]:
        structural_prefix = 2
    else:
        structural_prefix = 1
    safe_parts = [
        segment if index < structural_prefix or not segment else _digest(segment)
        for index, segment in enumerate(path_parts)
    ]
    safe_path = "/".join(safe_parts) or "/"
    return urlunsplit((parts.scheme, netloc, safe_path, "", ""))


def _safe_headers(headers: Mapping[str, str] | HTTPMessage) -> dict[str, str]:
    """Keep only non-secret response metadata useful for diagnostics."""

    allowed = {"content-type", "content-length", "etag", "date", "cache-control", "allow"}
    result: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in allowed:
            result[lower] = str(value)
    return result


@dataclass(frozen=True)
class ProbeEvent:
    """One redacted HTTP exchange suitable for an interop record."""

    operation: str
    started_at: str
    duration_ms: int
    request_method: str
    request_url: str
    request_headers: Mapping[str, str]
    request_body: Any | None
    response_status: int | None
    response_headers: Mapping[str, str]
    response_body: Any | None
    response_sha256: str | None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "startedAt": self.started_at,
            "durationMs": self.duration_ms,
            "request": {
                "method": self.request_method,
                "url": self.request_url,
                "headers": dict(self.request_headers),
                "body": self.request_body,
            },
            "response": {
                "status": self.response_status,
                "headers": dict(self.response_headers),
                "body": self.response_body,
                "sha256": self.response_sha256,
            },
            "error": self.error,
        }


@dataclass
class ProbeRecorder:
    """Collect redacted events and write a deterministic JSON record."""

    events: list[ProbeEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    secrets: tuple[str, ...] = ()

    def add(self, event: ProbeEvent) -> None:
        self.events.append(event)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "moonjmap.real-interop.v1",
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "metadata": redact_json(self.metadata, secrets=self.secrets),
            "events": [event.to_json() for event in self.events],
        }

    def write(self, destination: str | Path | TextIO) -> None:
        payload = json.dumps(self.to_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if hasattr(destination, "write"):
            destination.write(payload)  # type: ignore[union-attr]
            return
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


@dataclass(frozen=True)
class SessionInfo:
    """Small validated projection of a JMAP Session response."""

    raw: Mapping[str, Any]

    @property
    def api_url(self) -> str:
        value = self.raw.get("apiUrl")
        if not isinstance(value, str) or not value:
            raise ProbeError("JMAP Session did not provide a non-empty apiUrl")
        return value

    @property
    def primary_accounts(self) -> Mapping[str, Any]:
        value = self.raw.get("primaryAccounts", {})
        return value if isinstance(value, Mapping) else {}

    @property
    def accounts(self) -> Mapping[str, Any]:
        value = self.raw.get("accounts", {})
        return value if isinstance(value, Mapping) else {}

    def choose_account(self, requested: str | None = None) -> str:
        if requested is not None:
            if not isinstance(requested, str) or not requested:
                raise ProbeError("account_id must be a non-empty string")
            if self.accounts and requested not in self.accounts:
                raise ProbeError("requested account_id is absent from Session.accounts")
            return requested
        mail_urn = "urn:ietf:params:jmap:mail"
        primary = self.primary_accounts.get(mail_urn)
        if isinstance(primary, str) and primary:
            return primary
        for account_id, account in self.accounts.items():
            if isinstance(account_id, str) and isinstance(account, Mapping):
                capabilities = account.get("accountCapabilities", {})
                if isinstance(capabilities, Mapping) and mail_urn in capabilities:
                    return account_id
        raise ProbeError("Session has no discoverable Mail account; pass --account-id")


class JmapHttpProbe:
    """Opt-in read-only HTTP adapter for a single JMAP service."""

    def __init__(
        self,
        session_url: str,
        *,
        token: str | None = None,
        basic_auth: str | None = None,
        timeout: float = 20.0,
        allow_network: bool = False,
        insecure_tls: bool = False,
        recorder: ProbeRecorder | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not isinstance(session_url, str) or not session_url:
            raise ProbeError("session_url must be a non-empty URL")
        parts = urlsplit(session_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ProbeError("session_url must use http or https and include a host")
        if parts.username or parts.password:
            raise ProbeError("session_url must not contain userinfo")
        if timeout <= 0:
            raise ProbeError("timeout must be positive")
        if token and basic_auth:
            raise ProbeError("configure either Bearer token or Basic credentials, not both")
        if basic_auth is not None:
            if ":" not in basic_auth:
                raise ProbeError("basic_auth must use USERNAME:PASSWORD form")
            username, password = basic_auth.split(":", 1)
            if not username or not password:
                raise ProbeError("basic_auth username and password must be non-empty")
        self.session_url = session_url
        self.token = token
        self.basic_auth = basic_auth
        self.timeout = timeout
        self.allow_network = allow_network
        if insecure_tls and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ProbeError("insecure_tls is restricted to loopback session URLs")
        self.insecure_tls = insecure_tls
        self.recorder = recorder or ProbeRecorder()
        if token:
            secret_values = [token]
            if token.lower().startswith("bearer "):
                secret_values.append(token[7:].strip())
            for secret in secret_values:
                if secret and secret not in self.recorder.secrets:
                    self.recorder.secrets = (*self.recorder.secrets, secret)
        if basic_auth:
            username, password = basic_auth.split(":", 1)
            for secret in (basic_auth, username, password):
                if secret and secret not in self.recorder.secrets:
                    self.recorder.secrets = (*self.recorder.secrets, secret)
        if opener is not None:
            self._opener = opener
        elif insecure_tls:
            context = ssl._create_unverified_context()
            self._opener = lambda request, timeout: urlopen(request, timeout=timeout, context=context)
        else:
            self._opener = urlopen
        self._session: SessionInfo | None = None

    def _require_network(self) -> None:
        if not self.allow_network:
            raise NetworkDisabled("network disabled; pass allow_network=True explicitly")

    def _url_for_api(self, account_id: str | None = None) -> str:
        if self._session is None:
            raise ProbeError("call get_session() before using the JMAP API")
        endpoint = self._session.api_url
        if account_id is not None and "{accountId}" in endpoint:
            endpoint = endpoint.replace("{accountId}", quote(account_id, safe=""))
        return urljoin(self.session_url, endpoint)

    @staticmethod
    def _json_body(raw: bytes) -> Any:
        try:
            return json.loads(raw.decode("utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ProbeError(f"JMAP response was not valid JSON: {exc}") from exc

    def _http_json(self, operation: str, method: str, url: str, body: Any | None = None) -> Any:
        self._require_network()
        raw_request: bytes | None = None
        if body is not None:
            raw_request = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json", "User-Agent": "moonjmap-interop-probe/0.1"}
        if raw_request is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = (
                self.token if self.token.lower().startswith("bearer ") else f"Bearer {self.token}"
            )
        elif self.basic_auth:
            encoded = base64.b64encode(self.basic_auth.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        request = Request(url, data=raw_request, headers=headers, method=method)
        started = datetime.now(timezone.utc)
        clock = time.monotonic()
        response_status: int | None = None
        response_headers: Mapping[str, str] = {}
        response_body: Any | None = None
        response_bytes = b""
        error: str | None = None
        try:
            with self._opener(request, timeout=self.timeout) as response:
                response_status = int(response.status)
                response_headers = _safe_headers(response.headers)
                response_bytes = response.read()
            response_body = self._json_body(response_bytes)
            if response_status < 200 or response_status >= 300:
                raise ProbeError(f"HTTP {response_status} from JMAP service")
            return response_body
        except HTTPError as exc:
            response_status = int(exc.code)
            response_headers = _safe_headers(exc.headers)
            try:
                response_bytes = exc.read()
                response_body = self._json_body(response_bytes)
            except Exception:
                response_body = None
            error = f"HTTP {response_status} from JMAP service"
            raise ProbeError(error) from exc
        except URLError as exc:
            error = f"transport error: {exc.reason.__class__.__name__}"
            raise ProbeError(error) from exc
        except (TimeoutError, OSError) as exc:
            error = f"transport error: {exc.__class__.__name__}"
            raise ProbeError(error) from exc
        except Exception as exc:
            error = str(exc) if isinstance(exc, (ProbeError, ProtocolFailure)) else exc.__class__.__name__
            raise
        finally:
            elapsed = int(round((time.monotonic() - clock) * 1000))
            request_body = redact_json(body, secrets=self.recorder.secrets)
            self.recorder.add(
                ProbeEvent(
                    operation=operation,
                    started_at=started.isoformat().replace("+00:00", "Z"),
                    duration_ms=elapsed,
                    request_method=method,
                    request_url=safe_url(url),
                    request_headers=_safe_headers(headers),
                    request_body=request_body,
                    response_status=response_status,
                    response_headers=response_headers,
                    response_body=redact_json(response_body, secrets=self.recorder.secrets),
                    response_sha256=hashlib.sha256(response_bytes).hexdigest() if response_bytes else None,
                    error=error,
                )
            )

    def get_session(self) -> SessionInfo:
        payload = self._http_json("Session", "GET", self.session_url)
        if not isinstance(payload, Mapping):
            raise ProbeError("JMAP Session response must be an object")
        self._session = SessionInfo(dict(payload))
        self.recorder.metadata.update(
            {
                "sessionUrl": safe_url(self.session_url),
                "apiUrl": safe_url(urljoin(self.session_url, self._session.api_url)),
                "accountSelection": "explicit or primary Mail account",
            }
        )
        return self._session

    def call(self, request: JmapRequest, *, operation: str = "JMAP API") -> JmapResponse:
        if not isinstance(request, JmapRequest):
            raise ProbeError("request must be a JmapRequest")
        # RFC 8620 permits an apiUrl containing ``{accountId}``.  The fixed
        # MoonJMAP requests always carry accountId in their first method call,
        # so substitute it here without widening the public API.
        account_id: str | None = None
        first_args = request.method_calls[0].arguments
        candidate = first_args.get("accountId")
        if isinstance(candidate, str) and candidate:
            account_id = candidate
        body = self._http_json(operation, "POST", self._url_for_api(account_id), request.to_wire())
        try:
            return JmapResponse.from_wire(body)
        except ProtocolFailure:
            raise

    def call_one(self, request: JmapRequest, *, operation: str = "JMAP API") -> MethodResponse:
        response = self.call(request, operation=operation)
        if len(response.method_responses) != 1:
            raise ProbeError("probe expected one method response")
        return response.method_responses[0]

    def email_query(self, account_id: str, filter: Mapping[str, Any], *, position: int = 0, limit: int | None = None, call_id: str = "q1") -> Any:
        request = JmapRequest((EmailQueryRequest(account_id, filter, position=position, limit=limit, call_id=call_id).to_call(),))
        return self.call_one(request, operation="Email/query").decode_typed()

    def email_query_changes(self, account_id: str, filter: Mapping[str, Any], since_query_state: str, *, max_changes: int | None = None, call_id: str = "qc1", calculate_total: bool = False) -> Any:
        request = JmapRequest((EmailQueryChangesRequest(account_id, filter, since_query_state, max_changes=max_changes, call_id=call_id, calculate_total=calculate_total).to_call(),))
        return self.call_one(request, operation="Email/queryChanges").decode_typed()

    def email_get(self, account_id: str, ids: Sequence[str], *, call_id: str = "g1") -> Any:
        request = JmapRequest((EmailGetRequest(account_id, ids, call_id=call_id).to_call(),))
        return self.call_one(request, operation="Email/get").decode_typed()

    def email_changes(self, account_id: str, since_state: str, *, max_changes: int | None = None, call_id: str = "c1") -> Any:
        request = JmapRequest((EmailChangesRequest(account_id, since_state, max_changes=max_changes, call_id=call_id).to_call(),))
        return self.call_one(request, operation="Email/changes").decode_typed()


def run_read_only_scenario(
    probe: JmapHttpProbe,
    *,
    account_id: str | None,
    mailbox_id: str,
    limit: int = 20,
    max_changes: int = 50,
) -> dict[str, Any]:
    """Execute Session + query/get/changes/queryChanges and return summaries.

    The scenario makes no mutating JMAP call.  ``Email/changes`` starts at the
    state returned by the first ``Email/get`` and ``Email/queryChanges`` starts
    at the first query state, so a compliant server should normally return an
    empty delta.  A method error is recorded as a result summary rather than
    silently treated as success.
    """

    session = probe.get_session()
    selected = session.choose_account(account_id)
    query_filter = {"inMailbox": mailbox_id}
    query = probe.email_query(selected, query_filter, limit=limit)
    summary: dict[str, Any] = {"accountId": selected, "methods": {"Session": "ok"}}

    def add_result(name: str, value: Any) -> None:
        if isinstance(value, JmapMethodError):
            summary["methods"][name] = {"errorType": value.type}
        else:
            summary["methods"][name] = {"type": value.__class__.__name__}

    add_result("Email/query", query)
    query_state = getattr(query, "query_state", None)
    ids = list(getattr(query, "ids", ()))
    if query_state is None:
        return summary
    fetched = probe.email_get(selected, ids)
    add_result("Email/get", fetched)
    email_state = getattr(fetched, "state", None)
    if email_state is not None:
        changes = probe.email_changes(selected, email_state, max_changes=max_changes)
        add_result("Email/changes", changes)
    query_changes = probe.email_query_changes(selected, query_filter, query_state, max_changes=max_changes)
    add_result("Email/queryChanges", query_changes)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only, redacted MoonJMAP JMAP interoperability probe")
    parser.add_argument("--session-url", required=True, help="JMAP Session URL")
    parser.add_argument("--token-env", default="JMAP_TOKEN", help="environment variable containing Bearer token")
    parser.add_argument("--basic-env", help="environment variable containing USERNAME:PASSWORD for Basic auth")
    parser.add_argument("--account-id", help="JMAP Mail account id; otherwise use Session.primaryAccounts")
    parser.add_argument("--mailbox-id", help="mailbox id for the read-only query scenario")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-changes", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--insecure-tls", action="store_true", help="allow self-signed TLS only for localhost/loopback")
    parser.add_argument("--record", required=True, help="redacted JSON record output path")
    parser.add_argument("--allow-network", action="store_true", help="required safety acknowledgement")
    parser.add_argument("--session-only", action="store_true", help="only GET Session; do not call mail methods")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error("refusing network access without --allow-network")
    token = None
    if args.token_env:
        token = os.environ.get(args.token_env)
    basic_auth = os.environ.get(args.basic_env) if args.basic_env else None
    recorder = ProbeRecorder(
        metadata={
            "probe": "read-only",
            "authSource": (f"basic-env:{args.basic_env}" if args.basic_env else f"bearer-env:{args.token_env or 'none'}"),
        }
    )
    probe = JmapHttpProbe(
        args.session_url,
        token=token,
        basic_auth=basic_auth,
        timeout=args.timeout,
        allow_network=True,
        insecure_tls=args.insecure_tls,
        recorder=recorder,
    )
    try:
        if args.session_only:
            probe.get_session()
        else:
            if not args.mailbox_id:
                parser.error("--mailbox-id is required unless --session-only is used")
            run_read_only_scenario(
                probe,
                account_id=args.account_id,
                mailbox_id=args.mailbox_id,
                limit=args.limit,
                max_changes=args.max_changes,
            )
    except (ProbeError, ProtocolFailure, ValueError) as exc:
        recorder.metadata["status"] = "failed"
        recorder.metadata["errorType"] = exc.__class__.__name__
        recorder.write(args.record)
        print(f"probe failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    recorder.metadata["status"] = "ok"
    recorder.write(args.record)
    print(args.record)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through CLI smoke
    raise SystemExit(main())

