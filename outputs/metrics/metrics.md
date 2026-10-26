# MoonJMAP 合成视图指标报告

> 本报告来自固定增量向量与本地状态投影，只用于解释同步成本和预算行为。它不包含真实 JMAP 服务、网络耗时、吞吐、认证或互操作结论。

- fixture：`tests/vectors/incremental_cases.json`
- fixture SHA-256：`84471c1099c9ee932b7114b9ebd51069b44032a464faa154dac980baac86fabf`
- scenario 数：`15`
- trace schema：`v2`

## 指标定义

- `requests_attempted`：one observed response event corresponds to one attempted call; plan-only calls stay in requests_planned
- `response_bytes`：only an explicit response_bytes/bytes field from the fixture; current vectors provide none
- `objects_received`：Email/get list object count; notFound is counted separately
- `query_rebuilds`：query_result plus query history invalidation fallback
- `email_rebuilds`：Email history invalidation fallback
- `budget_termination`：declared vector max_rounds or max_calls prevents more work
- `timing`：not measured; no live transport
- `memory`：not measured; no live transport

## 汇总

| 指标 | 数值 |
|---|---:|
| `budget_terminations` | 2 |
| `control_events` | 8 |
| `email_created` | 0 |
| `email_destroyed` | 0 |
| `email_rebuilds` | 1 |
| `email_updated` | 1 |
| `not_found_objects` | 0 |
| `objects_received` | 6 |
| `query_added` | 3 |
| `query_fill_requests` | 2 |
| `query_rebuilds` | 4 |
| `query_reconciliation_required` | 1 |
| `query_removed` | 4 |
| `requested_objects` | 6 |
| `requests_attempted` | 21 |
| `requests_planned` | 4 |
| `response_bytes_available` | 0 |
| `responses_accepted` | 20 |
| `responses_dropped` | 1 |
| `responses_observed` | 21 |
| `responses_total` | 21 |
| `rounds_accepted` | 20 |
| `stale_responses_dropped` | 1 |
| `unique_objects_received` | 6 |
| `unsupported` | 1 |

## 场景

| 场景 | 状态 | 请求规划数 | 接受响应 | 丢弃响应 | 字节 | 对象 | 重建 | 预算终止 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `C01` 顺序不变但 a 的 keywords 改变 | Ready | 0 | 2 | 0 | 不可用 | 1 | 0 | — |
| `C02` b 从前缀中移出后按同一个 queryState 补位 | Ready | 0 | 3 | 0 | 不可用 | 1 | 0 | — |
| `C03` 同一个 ID 先 remove 后 add 时按新 index 处理 | Ready | 0 | 2 | 0 | 不可用 | 1 | 0 | — |
| `C04` removed 包含本地未缓存 ID | Ready | 0 | 1 | 0 | 不可用 | 0 | 0 | — |
| `C05` 补位返回不同 queryState，拒绝混接 | NeedsRefresh | 0 | 2 | 0 | 不可用 | 0 | 0 | — |
| `C06` Email changes 历史失效而 queryState 仍有效 | NeedsRefresh | 0 | 2 | 0 | 不可用 | 1 | 1 | — |
| `C07` queryChanges 历史失效而 Email state 仍有效 | NeedsRefresh | 0 | 1 | 0 | 不可用 | 0 | 1 | — |
| `C08` 窗口外邮件进入筛选时继续追赶 | Pending | 0 | 2 | 0 | 不可用 | 1 | 0 | — |
| `C09` get 观测到超前 Email state，不能跳过 Email changes | NeedsRefresh | 0 | 1 | 0 | 不可用 | 1 | 0 | — |
| `C10` 旧请求响应晚到时按 generation 丢弃 | Ready | 0 | 0 | 1 | 不可用 | 0 | 0 | — |
| `C11` maxCallsInRequest=1 时拆分请求 | Ready | 2 | 0 | 0 | 不可用 | 0 | 0 | — |
| `C12` maxObjectsInGet 小于前缀时分段并保留 Pending | Pending | 2 | 0 | 0 | 不可用 | 0 | 0 | call_budget_exhausted |
| `C13` 服务端不支持固定 filter/sort | Unsupported | 0 | 0 | 0 | 不可用 | 0 | 0 | — |
| `C14` 持续变化超出轮数预算 | Pending | 0 | 1 | 0 | 不可用 | 0 | 0 | round_budget_exhausted |
| `C15` 空列表、短列表和恰好 N 条不制造缺口 | Ready | 0 | 3 | 0 | 不可用 | 0 | 3 | — |

## 证据边界

每个场景的脱敏逐步 trace 位于 `traces/`。trace 只写方法、状态、计数、哈希和决策原因，不写邮件正文、地址、附件或服务凭据。若需要真实互操作或性能结论，必须另行取得服务版本、脱敏原始响应和网络测量记录。
