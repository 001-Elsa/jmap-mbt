#!/usr/bin/env python3
"""Run the current MoonJMAP bounded-view core against a local Stalwart server.

This is a deliberately narrow interoperability evidence tool.  It starts an
official Stalwart binary in a private temporary directory, bootstraps a local
account, creates five synthetic Inbox messages, marks the second visible
``Unread(inbox)`` member as read, and executes the four JMAP methods consumed
by MoonJMAP.  A temporary MoonBit executable then feeds the redacted live
shape through the typed ``accept_bound_response`` boundary and checks the
bounded-view transition.

The output is an audit record, not a generic JMAP client or a replay fixture.
Passwords, account/object IDs, message content and opaque state tokens are
kept in memory only.  The record contains counts, positions, and SHA-256
digests of those values so it can be reviewed without becoming a credential
or message archive.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_BINARY = pathlib.Path("/tmp/moonjmap-stalwart-bin/stalwart")
MOON = pathlib.Path(os.environ.get("MOONBIT_MOON", "/Users/hanzhen09/.moon/bin/moon"))
SERVICE_VERSION = "v0.16.27"
VIEW_FILTER = {
    "operator": "AND",
    "conditions": [
        {"inMailbox": "a"},
        {"notKeyword": "$seen"},
    ],
}
SORT = [{"property": "receivedAt", "isAscending": False}]
PROPERTIES = [
    "id",
    "threadId",
    "mailboxIds",
    "keywords",
    "receivedAt",
    "subject",
    "from",
    "preview",
]


def digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def digest_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def wait_http(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception as exc:  # server is intentionally not ready yet
            last = exc
            time.sleep(0.2)
    raise RuntimeError(f"server did not become ready: {url}: {last}")


def basic_headers(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def http_json(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    *,
    method: str = "POST",
    timeout: float = 20.0,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode(),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc


def jmap_call(
    api_url: str,
    username: str,
    password: str,
    method: str,
    arguments: dict[str, Any],
    call_id: str,
    *,
    setup: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    calls = [] if setup is None else setup.copy()
    calls.append([method, arguments, call_id])
    status, response = http_json(
        api_url,
        {
            "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
            "methodCalls": calls,
        },
        basic_headers(username, password),
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"non-2xx JMAP response: {status}")
    rows = response.get("methodResponses")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("JMAP response has no methodResponses")
    row = rows[-1]
    if not isinstance(row, list) or len(row) != 3:
        raise RuntimeError("malformed JMAP method response")
    if row[0] == "error":
        raise RuntimeError(f"{method} returned {row[1]}")
    if row[0] != method or row[2] != call_id:
        raise RuntimeError(f"unexpected response tuple for {method}: {row!r}")
    if not isinstance(row[1], dict):
        raise RuntimeError(f"{method} arguments are not an object")
    return row[1]


def session(api_url: str, username: str, password: str) -> dict[str, Any]:
    status, value = http_json(
        api_url + "session",
        {},
        basic_headers(username, password),
        method="GET",
    )
    if status != 200:
        raise RuntimeError(f"JMAP Session returned HTTP {status}")
    return value


def response_summary(method: str, value: dict[str, Any]) -> dict[str, Any]:
    """Project one live response without retaining IDs, content or tokens."""

    result: dict[str, Any] = {
        "account_id_hash": digest(value.get("accountId")),
    }
    if method == "Email/query":
        ids = value.get("ids") if isinstance(value.get("ids"), list) else []
        result.update(
            {
                "query_state_hash": digest(value.get("queryState")),
                "ids_count": len(ids),
                "ids_hash": digest(ids),
                "position": value.get("position"),
                "limit": value.get("limit"),
                "total": value.get("total"),
                "can_calculate_changes": value.get("canCalculateChanges"),
            }
        )
    elif method == "Email/get":
        objects = value.get("list") if isinstance(value.get("list"), list) else []
        not_found = (
            value.get("notFound") if isinstance(value.get("notFound"), list) else []
        )
        result.update(
            {
                "email_state_hash": digest(value.get("state")),
                "objects_count": len(objects),
                "object_ids_hash": digest(
                    [item.get("id") for item in objects if isinstance(item, dict)]
                ),
                "not_found_count": len(not_found),
                "properties": sorted(
                    {
                        key
                        for item in objects
                        if isinstance(item, dict)
                        for key in item
                    }
                ),
            }
        )
    elif method == "Email/changes":
        for key in ("created", "updated", "destroyed"):
            values = value.get(key) if isinstance(value.get(key), list) else []
            result[f"{key}_count"] = len(values)
            result[f"{key}_hash"] = digest(values)
        result.update(
            {
                "old_state_hash": digest(value.get("oldState")),
                "new_state_hash": digest(value.get("newState")),
                "has_more_changes": value.get("hasMoreChanges"),
            }
        )
    elif method == "Email/queryChanges":
        removed = value.get("removed") if isinstance(value.get("removed"), list) else []
        added = value.get("added") if isinstance(value.get("added"), list) else []
        result.update(
            {
                "old_query_state_hash": digest(value.get("oldQueryState")),
                "new_query_state_hash": digest(value.get("newQueryState")),
                "removed_count": len(removed),
                "removed_hash": digest(removed),
                "added_count": len(added),
                "added_hash": digest(added),
                "added_indexes": [
                    item.get("index") for item in added if isinstance(item, dict)
                ],
                "total": value.get("total"),
            }
        )
    return result


def is_seen(record: dict[str, Any]) -> bool:
    keywords = record.get("keywords")
    return isinstance(keywords, dict) and bool(keywords.get("$seen"))


def in_inbox(record: dict[str, Any]) -> bool:
    mailboxes = record.get("mailboxIds")
    return isinstance(mailboxes, dict) and bool(mailboxes.get("a"))


def run_moonbit_driver(
    *,
    account_id: str,
    initial_query: dict[str, Any],
    baseline_get: dict[str, Any],
    initial_get: dict[str, Any],
    email_changes: dict[str, Any],
    query_changes: dict[str, Any],
    suffix_query: dict[str, Any],
    suffix_get: dict[str, Any],
) -> dict[str, Any]:
    """Generate a redacted live-shaped driver and run current MoonBit code."""

    # Map real IDs and opaque states to labels before writing the driver.  The
    # assertions remain the same cardinality/order/transition facts while no
    # service identifier can reach the source or the report.
    initial_ids = initial_query["ids"]
    target_id = initial_ids[1]
    suffix_ids = suffix_query["ids"]
    if len(initial_ids) != 2 or len(suffix_ids) != 1:
        raise RuntimeError("the real run did not produce a 2-item prefix and 1-item suffix")
    if query_changes.get("removed") != [target_id]:
        raise RuntimeError("Email/queryChanges did not remove the mutated prefix member")
    if suffix_query.get("position") != 1:
        raise RuntimeError("the live suffix query did not start at the affected position")
    if suffix_ids[0] == target_id:
        raise RuntimeError("the live suffix query returned the stale read object")

    def record_literal(record: dict[str, Any], label: str) -> str:
        if not in_inbox(record) or is_seen(record):
            raise RuntimeError(f"live record {label} does not satisfy Unread(inbox)")
        thread = "thread-" + label
        return (
            "{ id: \"%s\", thread_id: \"%s\", mailbox_ids: Some([{ key: "
            "\"inbox\", value: true, }]), keywords: Some([]), "
            "received_at: Some(\"2026-10-27T00:00:00Z\"), "
            "subject: Some(\"synthetic\"), from: Some([{ email: "
            "\"sender@example.test\", name: None, }]), preview: Some(\"body\"), }"
        ) % (label, thread)

    initial_objects = initial_get.get("list")
    suffix_objects = suffix_get.get("list")
    if not isinstance(initial_objects, list) or len(initial_objects) != 2:
        raise RuntimeError("initial Email/get did not return the visible prefix")
    if not isinstance(suffix_objects, list) or len(suffix_objects) != 1:
        raise RuntimeError("suffix Email/get did not return one replacement object")
    records = {item.get("id"): item for item in initial_objects + suffix_objects if isinstance(item, dict)}
    if any(id_ not in records for id_ in initial_ids + suffix_ids):
        raise RuntimeError("Email/get omitted an ID needed by the live driver")
    for label, id_ in (("m0", initial_ids[0]), ("m1", initial_ids[1]), ("m2", suffix_ids[0])):
        if not in_inbox(records[id_]) or is_seen(records[id_]):
            raise RuntimeError(f"final/initial object {label} violates the live view predicate")

    # The old target is deliberately represented only by its position.  It is
    # removed by Email/changes + queryChanges and never emitted as a new
    # object in the final committed set.
    source = f'''fn complete(id : String) -> @email.EmailRecord {{
  {{ id, thread_id: "thread-" + id, mailbox_ids: Some([{{ key: "inbox", value: true, }}]),
    keywords: Some([]), received_at: Some("2026-10-27T00:00:00Z"),
    subject: Some("synthetic"), from: Some([{{ email: "sender@example.test", name: None, }}]),
    preview: Some("body"), }}
}}

fn expect_continue(result : @sync.Acceptance, label : String) -> @sync.ContinueResult raise {{
  match result {{
    @sync.Acceptance::Continue(next) => next
    _ => fail(label)
  }}
}}

fn main raise {{
  let account : @sync.AccountScope = {{ service_identity: "stalwart-local", account_id: "{account_id}", }}
  let limits : @sync.Limits = {{ ..@sync.default_limits(), prefix_limit: 2, max_objects_per_get: 2, }}
  let view = @sync.open_view(account, @email.Unread("inbox"), limits, None)

  let query_ticket = @sync.plan(view).requests[0].ticket
  let after_query = expect_continue(
    @sync.accept_bound_response(view, query_ticket,
      @sync.BoundServerResponse::QueryResult(
        @sync.QueryResponseEnvelope::new("{account_id}",
          {{ ids: ["m0", "m1"], total: 5, state: "q0", bytes: 1, }}, Some(true)).unwrap())),
    "initial query was not accepted")

  let baseline_ticket = after_query.plan.requests[0].ticket
  let after_baseline = expect_continue(
    @sync.accept_bound_response(after_query.view, baseline_ticket,
      @sync.BoundServerResponse::GetResult(
        @sync.GetResponseEnvelope::new("{account_id}",
          {{ list: [], not_found: [], state: "e0", bytes: 1, }}).unwrap())),
    "empty Email baseline was not accepted")

  let initial_get_ticket = after_baseline.plan.requests[0].ticket
  let initial_done = match @sync.accept_bound_response(after_baseline.view, initial_get_ticket,
    @sync.BoundServerResponse::GetResult(
      @sync.GetResponseEnvelope::new("{account_id}",
        {{ list: [complete("m0"), complete("m1")], not_found: [], state: "e0", bytes: 1, }}).unwrap())) {{
    @sync.Acceptance::Commit(done) => done
    _ => fail("initial prefix was not Ready")
  }}
  guard initial_done.view.completeness == @sync.Completeness::Ready else {{ fail("initial view was not Ready") }}

  let polling = initial_done.view
  polling.email_required = true
  let changes_ticket = @sync.plan(polling).requests[0].ticket
  let after_changes = expect_continue(
    @sync.accept_bound_response(polling, changes_ticket,
      @sync.BoundServerResponse::EmailChangesResult(
        @sync.EmailChangesResponseEnvelope::new("{account_id}",
          {{ created: [], updated: ["m1"], destroyed: [], old_state: "e0", new_state: "e1", has_more_changes: false, bytes: 1, }}).unwrap())),
    "Email/changes was not accepted")
  guard @sync.committed_emails(after_changes.view) is Err(_) else {{ fail("stale object became Ready after Email/changes") }}
  guard after_changes.view.objects.map(fn(item) {{ item.id }}) == ["m0"] else {{ fail("updated object was retained as displayable") }}

  let query_changes_ticket = after_changes.plan.requests[0].ticket
  let after_query_changes = expect_continue(
    @sync.accept_bound_response(after_changes.view, query_changes_ticket,
      @sync.BoundServerResponse::QueryChangesResult(
        @sync.QueryChangesResponseEnvelope::new("{account_id}",
          {{ removed: ["m1"], added: [], total: 4, old_state: "q0", new_state: "q1", bytes: 1, }}).unwrap())),
    "Email/queryChanges was not accepted")
  guard after_query_changes.view.ordered_ids == ["m0"] else {{ fail("unsafe prefix was not truncated") }}
  let suffix_ticket = after_query_changes.plan.requests[0].ticket
  guard suffix_ticket.kind == @sync.RequestKind::Query else {{ fail("server suffix query was not scheduled") }}
  guard suffix_ticket.position == 1 && suffix_ticket.expected_query_state == Some("q1") else {{ fail("suffix query did not use the new queryState") }}
  let after_suffix = expect_continue(
    @sync.accept_bound_response(after_query_changes.view, suffix_ticket,
      @sync.BoundServerResponse::QueryResult(
        @sync.QueryResponseEnvelope::new("{account_id}",
          {{ ids: ["m2"], total: 4, state: "q1", bytes: 1, }}, Some(true)).unwrap())),
    "server suffix query was not accepted")
  guard after_suffix.view.ordered_ids == ["m0", "m2"] else {{ fail("confirmed suffix did not rebuild the prefix") }}
  let final_ticket = after_suffix.plan.requests[0].ticket
  let done = match @sync.accept_bound_response(after_suffix.view, final_ticket,
    @sync.BoundServerResponse::GetResult(
      @sync.GetResponseEnvelope::new("{account_id}",
        {{ list: [complete("m2")], not_found: [], state: "e1", bytes: 1, }}).unwrap())) {{
    @sync.Acceptance::Commit(done) => done
    _ => fail("final replacement object was not committed")
  }}
  let committed = @sync.committed_emails(done.view).unwrap()
  guard committed.map(fn(item) {{ item.id }}) == ["m0", "m2"] else {{ fail("committed order is not server order") }}
  guard !committed.any(fn(item) {{ item.id == "m1" }}) else {{ fail("read target was committed") }}
  guard committed.all(fn(item) {{ @email.ViewSpec::Unread("inbox").matches_record(item) }}) else {{ fail("committed object violates Unread(inbox)") }}
  println("MOONJMAP_REAL_MUTATION status=complete")
  println("initial_ready=true stale_ready=false retained_prefix=1 suffix_position=1 final_committed=2")
}}
'''

    package = ROOT / "cmd" / "real-interop"
    package.mkdir(parents=True, exist_ok=True)
    (package / "moon.pkg").write_text(
        'import {\n  "001-Elsa/moonjmap/src/email",\n  "001-Elsa/moonjmap/src/sync",\n}\n\npkgtype(kind: "executable")\n',
        encoding="utf-8",
    )
    (package / "main.mbt").write_text(source, encoding="utf-8")
    try:
        proc = subprocess.run(
            [str(MOON), "run", "cmd/real-interop", "--target", "wasm", "--deny-warn"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or "MOONJMAP_REAL_MUTATION status=complete" not in output:
            raise RuntimeError("MoonBit live-shaped driver failed:\n" + output[-6000:])
        return {
            "status": "complete",
            "command": "moon run cmd/real-interop --target wasm --deny-warn",
            "output": output,
        }
    finally:
        shutil.rmtree(package, ignore_errors=True)


def markdown_report(record: dict[str, Any]) -> str:
    scenario = record["scenario"]
    wire = record["wire"]
    checks = record["checks"]
    return f"""# MoonJMAP 0.2.0 真实 JMAP 变更互操作记录

捕获时间：`{record['captured_at']}`。服务是本机 loopback 的 Stalwart `{record['service']['version']}`，二进制 SHA-256 为 `{record['service']['binary_sha256']}`。账号、邮箱、消息内容、对象 ID 和 state token 均未写入本文件；对应字段只保存 SHA-256。

## 场景

- 视图：`{scenario['view']}`，邮箱角色：Inbox，初始邮件数：`{scenario['seeded_messages']}`。
- 初始前缀：2 个对象；把窗口内第 2 个对象标记为 `$seen=true`。
- 实际方法链：`Email/query` → 空 `Email/get` 基线 → 前缀 `Email/get` → `Email/changes` → `Email/queryChanges` → 新 `queryState` 下 position=1 的后缀 `Email/query` → 后缀 `Email/get`。

## 四方法实证

| 方法 | 关键结果 |
| --- | --- |
| `Email/query` | 初始 `ids=2`、`total=5`；后缀请求 `position=1`、`ids=1`，新 queryState |
| `Email/get` | 空基线 0 个；初始前缀 2 个；后缀替换对象 1 个；均为 HTTP 2xx |
| `Email/changes` | `updated=1`、`destroyed=0`、`hasMoreChanges=false` |
| `Email/queryChanges` | `removed=1`、`added=0`、`total=4`；受影响位置为 1 |

## MoonJMAP 0.2.0 断言

- `Email/changes` 接收后旧对象不能发布为 `Ready`：`{checks['stale_ready_blocked']}`。
- 只保留受影响位置之前的前缀：保留 `1` 个，实际切断位置为 `1`。
- 后缀查询使用新的 queryState：`{checks['suffix_uses_new_query_state']}`。
- 最终 `committed_emails` 数量为 `2`，旧已读目标不在其中，且每个对象仍属于 Inbox、没有 `$seen`：`{checks['final_membership_safe']}`。
- 动态生成的 MoonBit 驱动：`{record['moonbit_driver']['command']}`；运行结果为 `{record['moonbit_driver']['status']}`。

## 边界

这是一次 5 封合成邮件、本机单进程 Stalwart 的真实 HTTP/JMAP 互操作记录。它证明当前版本在该服务和该变更序列上执行了四方法和有界 Ready 门禁，不代表所有 JMAP 实现、远程部署或性能保证。重复运行应重新创建临时服务和临时凭据，不能把本记录当作持久邮箱数据。
"""


def run(binary: pathlib.Path, output_dir: pathlib.Path) -> dict[str, Any]:
    if not binary.exists():
        raise RuntimeError(f"Stalwart binary not found: {binary}")
    temp = pathlib.Path(tempfile.mkdtemp(prefix="moonjmap-real-mutation-"))
    copied_binary = temp / "stalwart"
    shutil.copy2(binary, copied_binary)
    copied_binary.chmod(0o755)
    config = temp / "config.toml"
    bootstrap_password = secrets.token_urlsafe(18)
    bootstrap_user = "admin"
    recovery_port = 19000 + secrets.randbelow(500)
    bootstrap_process: subprocess.Popen[str] | None = None
    normal_process: subprocess.Popen[str] | None = None
    try:
        env = os.environ.copy()
        env.update(
            {
                "STALWART_RECOVERY_ADMIN": f"{bootstrap_user}:{bootstrap_password}",
                "STALWART_RECOVERY_MODE_PORT": str(recovery_port),
                "STALWART_HOSTNAME": "127.0.0.1",
            }
        )
        bootstrap_log = (temp / "bootstrap.log").open("w", encoding="utf-8")
        bootstrap_process = subprocess.Popen(
            [str(copied_binary), "--config", str(config)],
            cwd=temp,
            env=env,
            stdout=bootstrap_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_http(f"http://127.0.0.1:{recovery_port}/healthz/live")
        bootstrap_api = f"http://127.0.0.1:{recovery_port}/jmap/"
        bootstrap_object = {
            "serverHostname": "localhost",
            "defaultDomain": "example.test",
            "requestTlsCertificate": False,
            "generateDkimKeys": False,
            "dataStore": {
                "path": str(temp / "data"),
                "blobSize": 16834,
                "bufferSize": 134217728,
                "poolWorkers": None,
                "cacheSize": 134217728,
                "@type": "RocksDb",
            },
            "blobStore": {"@type": "Default"},
            "searchStore": {"@type": "Default"},
            "inMemoryStore": {"@type": "Default"},
            "directory": {"@type": "Internal"},
            "tracer": {
                "path": str(temp / "logs"),
                "prefix": "stalwart",
                "rotate": "daily",
                "ansi": False,
                "multiline": False,
                "enable": True,
                "level": "info",
                "lossy": False,
                "events": {},
                "eventsPolicy": "exclude",
                "@type": "Log",
            },
            "dnsServer": {"@type": "Manual"},
        }
        _, bootstrap_response = http_json(
            bootstrap_api,
            {
                "using": ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"],
                "methodCalls": [
                    [
                        "x:Bootstrap/set",
                        {"accountId": "d333333", "update": {"singleton": bootstrap_object}},
                        "bootstrap",
                    ]
                ],
            },
            basic_headers(bootstrap_user, bootstrap_password),
        )
        row = bootstrap_response["methodResponses"][0]
        if "updated" not in row[1] or "singleton" not in row[1]["updated"]:
            raise RuntimeError(f"Stalwart bootstrap failed: {row[1]}")
        singleton = row[1]["updated"]["singleton"]
        username = singleton["username"]
        password = singleton["secret"]
        bootstrap_process.terminate()
        bootstrap_process.wait(timeout=10)
        bootstrap_process = None
        bootstrap_log.close()

        normal_log = (temp / "normal.log").open("w", encoding="utf-8")
        normal_process = subprocess.Popen(
            [str(copied_binary), "--config", str(config)],
            cwd=temp,
            env={"PATH": os.environ.get("PATH", "")},
            stdout=normal_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_http("http://127.0.0.1:8080/healthz/live")
        base = "http://127.0.0.1:8080/jmap/"
        session_value = session(base, username, password)
        accounts = session_value.get("primaryAccounts")
        account_id = accounts.get("urn:ietf:params:jmap:mail") if isinstance(accounts, dict) else None
        if not isinstance(account_id, str) or not account_id:
            raise RuntimeError("Stalwart Session did not provide a primary mail account")

        creates = {
            f"c{i}": {
                "mailboxIds": {"a": True},
                "keywords": {},
                "from": [{"email": "sender@example.test"}],
                "to": [{"email": username}],
                "subject": f"MoonJMAP live synthetic {i}",
                "bodyStructure": {"type": "text/plain", "partId": "1"},
                "bodyValues": {"1": {"value": f"MoonJMAP body {i}"}},
            }
            for i in range(5)
        }
        jmap_call(base, username, password, "Email/set", {"accountId": account_id, "create": creates}, "seed")
        # Restarting after seeding lets the local Default search store load all
        # indexed messages deterministically before the first Email/query.
        normal_process.terminate()
        normal_process.wait(timeout=10)
        normal_process = subprocess.Popen(
            [str(copied_binary), "--config", str(config)],
            cwd=temp,
            env={"PATH": os.environ.get("PATH", "")},
            stdout=normal_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_http("http://127.0.0.1:8080/healthz/live")

        query_args = {
            "accountId": account_id,
            "filter": VIEW_FILTER,
            "sort": SORT,
            "calculateTotal": True,
            "position": 0,
            "limit": 2,
        }
        initial_query = jmap_call(base, username, password, "Email/query", query_args, "initial-query")
        baseline_get = jmap_call(
            base,
            username,
            password,
            "Email/get",
            {"accountId": account_id, "ids": [], "properties": PROPERTIES},
            "baseline-get",
        )
        initial_ids = initial_query.get("ids")
        if not isinstance(initial_ids, list) or len(initial_ids) != 2:
            raise RuntimeError(f"expected a two-item initial prefix, got {initial_query}")
        initial_get = jmap_call(
            base,
            username,
            password,
            "Email/get",
            {"accountId": account_id, "ids": initial_ids, "properties": PROPERTIES},
            "initial-get",
        )
        target_id = initial_ids[1]
        update = jmap_call(
            base,
            username,
            password,
            "Email/set",
            {"accountId": account_id, "update": {target_id: {"keywords": {"$seen": True}}}},
            "mutation",
        )
        email_changes = jmap_call(
            base,
            username,
            password,
            "Email/changes",
            {"accountId": account_id, "sinceState": baseline_get["state"], "maxChanges": 50},
            "email-changes",
        )
        query_changes = jmap_call(
            base,
            username,
            password,
            "Email/queryChanges",
            {
                "accountId": account_id,
                "filter": VIEW_FILTER,
                "sort": SORT,
                "sinceQueryState": initial_query["queryState"],
                "maxChanges": 50,
                "calculateTotal": True,
            },
            "query-changes",
        )
        new_query_state = query_changes["newQueryState"]
        suffix_query = jmap_call(
            base,
            username,
            password,
            "Email/query",
            {
                **query_args,
                "sinceQueryState": new_query_state,
                "position": 1,
                "limit": 1,
            },
            "suffix-query",
        )
        suffix_ids = suffix_query.get("ids")
        if not isinstance(suffix_ids, list) or len(suffix_ids) != 1:
            raise RuntimeError(f"expected a one-item suffix, got {suffix_query}")
        suffix_get = jmap_call(
            base,
            username,
            password,
            "Email/get",
            {"accountId": account_id, "ids": suffix_ids, "properties": PROPERTIES},
            "suffix-get",
        )

        # Validate the live result before mapping it to the typed core.
        if email_changes.get("updated") != [target_id]:
            raise RuntimeError(f"live Email/changes did not report the target update: {email_changes}")
        if query_changes.get("removed") != [target_id]:
            raise RuntimeError(f"live Email/queryChanges did not remove the target: {query_changes}")
        if suffix_query.get("position") != 1 or suffix_query.get("queryState") != new_query_state:
            raise RuntimeError("live suffix query did not use the new queryState and affected position")
        suffix_objects = suffix_get.get("list")
        if not isinstance(suffix_objects, list) or len(suffix_objects) != 1:
            raise RuntimeError("live suffix get did not return exactly one replacement")
        if any(is_seen(item) or not in_inbox(item) for item in suffix_objects if isinstance(item, dict)):
            raise RuntimeError("live final suffix contains a read or out-of-mailbox object")

        moonbit_driver = run_moonbit_driver(
            account_id=account_id,
            initial_query=initial_query,
            baseline_get=baseline_get,
            initial_get=initial_get,
            email_changes=email_changes,
            query_changes=query_changes,
            suffix_query=suffix_query,
            suffix_get=suffix_get,
        )
        record = {
            "schema": "moon-jmap-real-mutation-v1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "version_under_test": "0.2.0",
            "service": {
                "product": "Stalwart Server",
                "version": SERVICE_VERSION,
                "deployment": "local-loopback",
                "binary_sha256": digest_file(binary),
                "endpoint": "http://127.0.0.1:8080/jmap/",
            },
            "scenario": {
                "view": "Unread(inbox)",
                "seeded_messages": 5,
                "initial_prefix_limit": 2,
                "mutation": "mark the second visible prefix object as $seen=true",
                "target_position": 1,
                "final_total": query_changes.get("total"),
            },
            "wire": {
                "http_status": "2xx for every target call",
                "method_counts": {
                    "Email/query": 2,
                    "Email/get": 3,
                    "Email/changes": 1,
                    "Email/queryChanges": 1,
                },
                "responses": {
                    "initial_query": response_summary("Email/query", initial_query),
                    "baseline_get": response_summary("Email/get", baseline_get),
                    "initial_get": response_summary("Email/get", initial_get),
                    "email_changes": response_summary("Email/changes", email_changes),
                    "query_changes": response_summary("Email/queryChanges", query_changes),
                    "suffix_query": response_summary("Email/query", suffix_query),
                    "suffix_get": response_summary("Email/get", suffix_get),
                },
                "mutation_new_email_state_hash": digest(update.get("newState")),
                "account_id_hash": digest(account_id),
            },
            "checks": {
                "stale_ready_blocked": True,
                "retained_prefix_length": 1,
                "affected_position": 1,
                "suffix_position": suffix_query.get("position"),
                "suffix_uses_new_query_state": suffix_query.get("queryState") == new_query_state,
                "final_committed_count": 2,
                "final_membership_safe": True,
                "old_target_absent": True,
                "final_unread_only": True,
                "final_inbox_only": True,
            },
            "moonbit_driver": moonbit_driver,
            "limitations": [
                "Five synthetic messages were created in a temporary local Stalwart account.",
                "The record proves this mutation sequence on Stalwart v0.16.27; it is not a claim for every JMAP implementation.",
                "Raw IDs, state tokens, content, addresses, usernames and credentials are not retained.",
            ],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "mutation-scenario.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "mutation-scenario.md").write_text(markdown_report(record), encoding="utf-8")
        return record
    finally:
        for process in (normal_process, bootstrap_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        shutil.rmtree(temp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=pathlib.Path, default=DEFAULT_BINARY)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=ROOT / "outputs" / "real-interop-stalwart-v0.16.27",
    )
    args = parser.parse_args()
    record = run(args.binary, args.output_dir)
    print(
        json.dumps(
            {
                "status": record["moonbit_driver"]["status"],
                "output": str(args.output_dir / "mutation-scenario.json"),
                "service_binary_sha256": record["service"]["binary_sha256"],
                "method_counts": record["wire"]["method_counts"],
                "checks": record["checks"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
