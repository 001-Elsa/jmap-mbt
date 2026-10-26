from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.real_jmap_benchmark import _resolve_api_url, _safe_endpoint, parser, run_live


class _FakeJmapHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, *_args) -> None:  # pragma: no cover - test noise
        return

    def do_GET(self) -> None:
        if self.path != "/session":
            self.send_error(404)
            return
        body = {
            "capabilities": {
                "urn:ietf:params:jmap:core": {"maxCallsInRequest": 4},
                "urn:ietf:params:jmap:mail": {"maxObjectsInGet": 50},
            },
            "apiUrl": f"http://127.0.0.1:{self.server.server_port}/api",
            "accounts": {"acct-test": {"name": "redacted", "isPersonal": True}},
        }
        self._write(200, body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        self.calls.append(payload)
        method, args, call_id = payload["methodCalls"][0]
        if method == "Email/query":
            position = int(args.get("position", 0))
            ids = ["id-1", "id-2"][position: position + int(args.get("limit", 50))]
            body = {"methodResponses": [[method, {
                "accountId": args["accountId"],
                "queryState": "q-state-1",
                "ids": ids,
                "position": position,
                "total": 2,
                "canCalculateChanges": True,
            }, call_id]]}
        elif method == "Email/get":
            ids = args.get("ids", [])
            body = {"methodResponses": [[method, {
                "accountId": args["accountId"],
                "state": "e-state-1",
                "list": [{
                    "id": value,
                    "threadId": "t-1",
                    "mailboxIds": {"mbox-test": True},
                    "keywords": {},
                    "receivedAt": "2026-01-01T00:00:00Z",
                    "subject": "redacted",
                    "from": [{"email": "example.invalid", "name": None}],
                    "preview": "redacted",
                } for value in ids],
                "notFound": [],
            }, call_id]]}
        elif method == "Email/queryChanges":
            body = {"methodResponses": [[method, {
                "accountId": args["accountId"],
                "oldQueryState": args["sinceQueryState"],
                "newQueryState": "q-state-1",
                "removed": [],
                "added": [],
                "total": 2,
            }, call_id]]}
        elif method == "Email/changes":
            body = {"methodResponses": [[method, {
                "accountId": args["accountId"],
                "oldState": args["sinceState"],
                "newState": "e-state-1",
                "hasMoreChanges": False,
                "created": [],
                "updated": [],
                "destroyed": [],
            }, call_id]]}
        else:
            self.send_error(400)
            return
        self._write(200, body)

    def _write(self, status: int, body: dict) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class LiveBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeJmapHandler.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeJmapHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_live_report_has_wire_and_rtt_metrics_and_redacts_values(self) -> None:
        args = parser().parse_args([
            "--session-url", f"http://127.0.0.1:{self.server.server_port}/session",
            "--api-url", f"http://127.0.0.1:{self.server.server_port}/api",
            "--account-id", "acct-test",
            "--mailbox-id", "mbox-test",
            "--iterations", "2",
            "--prefix-limit", "1",
            "--max-objects", "1",
            "--allow-http",
        ])
        # run_live reads the token from this process environment; set it only
        # for the request and never inspect or serialize it in the report.
        import os
        old = os.environ.get("JMAP_ACCESS_TOKEN")
        os.environ["JMAP_ACCESS_TOKEN"] = "test-token-do-not-emit"
        try:
            report = run_live(args)
        finally:
            if old is None:
                os.environ.pop("JMAP_ACCESS_TOKEN", None)
            else:
                os.environ["JMAP_ACCESS_TOKEN"] = old
        self.assertEqual(report["status"], "complete")
        self.assertTrue(report["performance_claim"])
        self.assertGreater(report["metrics"]["request_bytes"], 0)
        self.assertGreater(report["metrics"]["response_bytes"], 0)
        self.assertGreater(report["metrics"]["rtt_ms"]["count"], 0)
        self.assertEqual(report["metrics"]["query_fill_requests"], 2)
        serialized = json.dumps(report, ensure_ascii=False)
        for raw in ("test-token-do-not-emit", "acct-test", "mbox-test", "id-1", "id-2", "redacted"):
            self.assertNotIn(raw, serialized)
        # First iteration has query + fill + get; the second adds
        # queryChanges + changes after its query + fill + get.
        self.assertEqual(len(_FakeJmapHandler.calls), 9)

    def test_live_run_without_token_is_blocked_after_session(self) -> None:
        import os
        old = os.environ.pop("JMAP_ACCESS_TOKEN", None)
        try:
            args = parser().parse_args([
                "--session-url", f"http://127.0.0.1:{self.server.server_port}/session",
                "--allow-http",
            ])
            report = run_live(args)
        finally:
            if old is not None:
                os.environ["JMAP_ACCESS_TOKEN"] = old
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["performance_claim"])
        self.assertEqual(report["session"]["status"], 200)
        self.assertIn("no bearer or basic credential", report["reason"])

    def test_relative_account_api_url_is_resolved_without_leaking_account(self) -> None:
        resolved = _resolve_api_url("/api/{accountId}", "https://example.invalid/jmap/session", "acct-private")
        self.assertEqual(resolved, "https://example.invalid/api/acct-private")
        self.assertNotIn("acct-private", json.dumps(_safe_endpoint(resolved)))

    def test_basic_auth_is_selected_when_bearer_is_absent(self) -> None:
        import os
        old = {key: os.environ.get(key) for key in ("JMAP_ACCESS_TOKEN", "JMAP_BASIC_USERNAME", "JMAP_BASIC_PASSWORD")}
        os.environ.pop("JMAP_ACCESS_TOKEN", None)
        os.environ["JMAP_BASIC_USERNAME"] = "acct-test"
        os.environ["JMAP_BASIC_PASSWORD"] = "password-not-emitted"
        try:
            args = parser().parse_args([
                "--session-url", f"http://127.0.0.1:{self.server.server_port}/session",
                "--api-url", f"http://127.0.0.1:{self.server.server_port}/api",
                "--account-id", "acct-test",
                "--mailbox-id", "mbox-test",
                "--iterations", "1",
                "--prefix-limit", "1",
                "--max-objects", "1",
                "--allow-http",
            ])
            report = run_live(args)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["authentication"], {"scheme": "basic", "credential_present": True})
        self.assertNotIn("password-not-emitted", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
