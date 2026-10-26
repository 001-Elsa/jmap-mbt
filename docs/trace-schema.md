# 可追溯同步 trace 格式（内部证据）

调试输出应记录每个计划和响应接纳边界，而不是只打印最终邮件 ID。下面是一个脱敏后可保存的 JSON 结构；它是主功能的诊断证据，不是持久化数据库 schema、通用日志格式或独立可观测性产品。

```json
{
  "trace_version": 1,
  "generation": 7,
  "account_scope_hash": "sha256:…",
  "query_key_hash": "sha256:…",
  "step": 3,
  "ticket": {
    "request_id": 12,
    "kind": "Email/queryChanges",
    "expected_query_state": "q0",
    "expected_email_state": "e4",
    "position": 0,
    "limit": 50
  },
  "response": {
    "method": "Email/queryChanges",
    "call_id": "qc3",
    "old_state": "q0",
    "new_state": "q1",
    "removed_count": 1,
    "added_count": 2,
    "bytes": 418
  },
  "decision": "Continue",
  "reason": "prefix gap requires same-state query",
  "before": {
    "ordered_ids_hash": "sha256:…",
    "total": 52,
    "query_state": "q0",
    "email_state": "e4",
    "completeness": "Pending"
  },
  "after": {
    "ordered_ids_hash": "sha256:…",
    "total": 53,
    "query_state": "q1",
    "email_state": "e4",
    "completeness": "Pending",
    "pending_work": ["get:…", "query-fill:position=49"]
  }
}
```

## 记录规则

* `generation`、`step`、`request_id` 用于重建顺序；同一请求的响应只能出现一次。
* 账号和查询使用 hash 或本地别名，不能写入 OAuth、Cookie、完整账号地址或原始服务 URL。
* response 只记录方法、call id、状态和计数；邮件正文、附件、header 全部省略。需要复核字段时使用合成 fixture 或单独脱敏文件。
* `before`、`after` 必须在状态接纳前后各快照一次；协议失败的 `after` 应保持旧 token，且 `decision` 为 `ProtocolFailure`。
* `Commit` 记录的 `after.completeness` 必须为 `Ready`，并同时引用视图和 checkpoint 的 hash；`Pending`/`NeedsRefresh` 必须记录 reason 和 pending_work。

## 证据关联

报告应同时写入 fixture SHA-256、代码 commit、运行命令和 trace 文件清单。缺少原始响应或服务版本时，trace 只能标为本地模型证据，不能上升为互操作结论。


## v2 本地指标扩展

`trace_version=2` 只扩展 MoonJMAP 邮件查询视图的诊断记录，不把 trace 设计成通用日志或持久化数据库格式。固定向量运行器会为每个场景保存一个脱敏 JSON 文件，路径在 [outputs/metrics/metrics.json](../outputs/metrics/metrics.json) 的 `trace_files` 中列出。

v2 在文档开头的单请求记录之外增加以下字段。`run_id` 由 fixture hash、范围和 schema 计算，不含时间戳，因此重复运行可直接比较：

```json
{
  "trace_version": 2,
  "run_id": "synthetic-…",
  "scenario_id": "C02",
  "implementation": "vector-projection",
  "evidence": "synthetic-local",
  "fixture_sha256": "…",
  "account_scope_hash": "sha256:…",
  "query_key_hash": "sha256:…",
  "capabilities": {"supportsFilter": true, "supportsSort": true},
  "limits": {"max_rounds": 3},
  "events": []
}
```

每个事件的 `before`、`after` 都包含 `ordered_ids_hash` 和 `state_hash`；待取 ID 只保留 `get_hash:sha256:…`，不写原始邮件 ID。`response` 只保留 method、状态、数量、决策和 ID 哈希；邮件对象字段、地址、正文、附件和服务凭据不进入 trace。`reason_code` 使用领域状态机原因，例如 `fill_query_state_mismatch`、`email_history_invalid`、`stale_response_discarded` 和 `budget_exhausted_before_response`。

现有向量没有服务端响应字节字段。因此 `response.bytes` 和场景汇总中的 `response_bytes` 必须为 `null`，并带 `bytes_source=unavailable`；不能用 JSON fixture 的文件长度冒充网络 payload。未来只有在脱敏 fixture 明确给出 `response_bytes`/`bytes` 时，运行器才会累计该字段。运行器同样不测量网络延迟、吞吐或内存。

运行器命令：

```sh
python3 scripts/benchmark_metrics.py
```

它生成 `outputs/metrics/metrics.json`、`outputs/metrics/metrics.md` 和每场景 `outputs/metrics/traces/Cxx.json`。这些文件是固定合成数据的本地证据，只能说明状态机在指定输入下发出了多少类请求、接纳了多少响应、发生了多少变更/重建以及何时被预算阻止；它们不能证明真实服务互操作、线上性能或认证结果。

v2 场景文件还包含 `controls` 和 `final`：`controls` 记录能力、限制、计划和 generation 切换等不产生服务响应的本地控制边界；`final` 是经过 fixture expected-state 校验后的终态快照，包含最终状态、原因码、数量和 ID 哈希。这样，只有旧响应或计划控制的场景也能完整重建“为何没有新的响应、为何仍为 Ready/Pending/Unsupported”。
