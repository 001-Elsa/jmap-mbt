"""Local HTTP-server tests for the opt-in, redacted JMAP probe."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from jmap import JmapMethodError
from jmap.http_probe import (
    JmapHttpProbe,
    NetworkDisabled,
    ProbeRecorder,
    ProbeError,
    redact_json,
    run_read_only_scenario,
    safe_url,
)


class _Handler(BaseHTTPRequestHandler):
    calls: list[tuple[str, dict[str, object] | None]] = []
    auth_headers: list[str] = []

    def log_message(self, *_args: object) -> None:  # pragma: no cover - quiet test server
        return

    def _send(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self.__class__.auth_headers.append(self.headers.get("Authorization", ""))
        self.__class__.calls.append(("GET", None))
        self._send(
            {
                "apiUrl": "/api/{accountId}",
                "primaryAccounts": {"urn:ietf:params:jmap:mail": "acct-private"},
                "accounts": {
                    "acct-private": {
                        "name": "Private Name",
                        "accountCapabilities": {"urn:ietf:params:jmap:mail": {}},
                    }
                },
                "capabilities": {"urn:ietf:params:jmap:core": {"maxCallsInRequest": 4}},
            }
        )

    def do_POST(self) -> None:  # noqa: N802
        self.__class__.auth_headers.append(self.headers.get("Authorization", ""))
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size))
        self.__class__.calls.append(("POST", payload))
        name, args, call_id = payload["methodCalls"][0]
        account = args["accountId"]
        if name == "Email/query":
            result = [name, {"accountId": account, "queryState": "query-private", "ids": ["email-private"], "position": 0, "total": 1, "canCalculateChanges": True}, call_id]
        elif name == "Email/get":
            result = [name, {"accountId": account, "state": "email-private", "list": [{"id": "email-private", "threadId": "thread-private", "mailboxIds": {"mailbox-private": True}, "keywords": {}, "receivedAt": "2026-01-01T00:00:00Z", "subject": "Private subject", "from": [{"email": "person@example.invalid"}], "preview": "Private body"}], "notFound": []}, call_id]
        elif name == "Email/changes":
            result = [name, {"accountId": account, "oldState": "email-private", "newState": "email-private", "hasMoreChanges": False, "created": [], "updated": [], "destroyed": []}, call_id]
        elif name == "Email/queryChanges":
            result = [name, {"accountId": account, "oldQueryState": "query-private", "newQueryState": "query-private", "removed": [], "added": [], "total": 1}, call_id]
        else:  # pragma: no cover - the client only sends the fixed four methods
            self._send({"methodResponses": [["error", {"type": "unknownMethod"}, call_id]]}, status=400)
            return
        self._send({"methodResponses": [result]})


class HttpProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _Handler.calls = []
        _Handler.auth_headers = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        _Handler.calls = []
        _Handler.auth_headers = []
        self.url = f"http://127.0.0.1:{self.server.server_port}/.well-known/jmap"

    def test_requires_explicit_network_permission(self) -> None:
        probe = JmapHttpProbe(self.url, token="secret-token")
        with self.assertRaises(NetworkDisabled):
            probe.get_session()
        self.assertEqual(_Handler.calls, [])

    def test_read_only_scenario_and_redacted_record(self) -> None:
        recorder = ProbeRecorder()
        probe = JmapHttpProbe(self.url, token="secret-token", allow_network=True, recorder=recorder)
        result = run_read_only_scenario(probe, account_id=None, mailbox_id="mailbox-private", limit=5)
        self.assertEqual(result["methods"]["Session"], "ok")
        self.assertEqual(result["methods"]["Email/query"]["type"], "EmailQueryResponse")
        self.assertEqual(result["methods"]["Email/get"]["type"], "EmailGetResponse")
        self.assertEqual(result["methods"]["Email/changes"]["type"], "EmailChangesResponse")
        self.assertEqual(result["methods"]["Email/queryChanges"]["type"], "EmailQueryChangesResponse")
        self.assertEqual(len(recorder.events), 5)
        payload = json.dumps(recorder.to_json(), ensure_ascii=False, sort_keys=True)
        for secret in ("secret-token", "acct-private", "mailbox-private", "email-private", "Private subject", "Private body", "person@example.invalid"):
            self.assertNotIn(secret, payload)
        self.assertIn("sha256:", payload)
        self.assertEqual(urlsplit(recorder.events[-1].request_url).query, "")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            recorder.write(path)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"], "moonjmap.real-interop.v1")
            self.assertEqual(loaded["metadata"]["status"] if "status" in loaded["metadata"] else None, None)

    def test_safe_url_and_redaction_helpers(self) -> None:
        self.assertEqual(safe_url("https://user:pass@example.test/a?token=secret#x"), "https://service.invalid/sha256:ca978112ca1bbdca")
        value = redact_json({"authorization": "Bearer secret-token", "unknown": "secret-token", "ids": ["a"], "subject": "hello"}, secrets=("secret-token",))
        rendered = json.dumps(value)
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("hello", rendered)
        self.assertTrue(value["ids"][0].startswith("sha256:"))
        self.assertEqual(redact_json({"apiUrl": "https://secret.example/jmap/api"})["apiUrl"], "https://service.invalid/jmap/api")

    def test_placeholder_api_url_is_substituted(self) -> None:
        recorder = ProbeRecorder()
        probe = JmapHttpProbe(self.url, allow_network=True, recorder=recorder)
        response = probe.get_session()
        value = probe.email_query(response.choose_account(), {"inMailbox": "mailbox-private"})
        self.assertFalse(isinstance(value, JmapMethodError))
        post_urls = [event.request_url for event in recorder.events if event.request_method == "POST"]
        self.assertTrue(post_urls[-1].startswith("http://service.invalid/api/sha256:"))
        self.assertNotIn("{accountId}", post_urls[-1])

    def test_basic_auth_is_sent_but_never_recorded(self) -> None:
        recorder = ProbeRecorder()
        probe = JmapHttpProbe(
            self.url,
            basic_auth="admin@example.test:private-password",
            allow_network=True,
            recorder=recorder,
        )
        probe.get_session()
        self.assertTrue(_Handler.auth_headers)
        self.assertTrue(all(value.startswith("Basic ") for value in _Handler.auth_headers))
        rendered = json.dumps(recorder.to_json(), ensure_ascii=False)
        self.assertNotIn("admin@example.test", rendered)
        self.assertNotIn("private-password", rendered)


if __name__ == "__main__":
    unittest.main()

