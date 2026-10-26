# MoonJMAP 邮件视图指标与预算基准（内部证据）

本基准是主功能的内部证据，不是独立产品。它面向 MoonJMAP 的固定范围：单账号、单个只读 Email 查询视图、有界连续前缀，以及 `Email/query`、`Email/queryChanges`、`Email/get`、`Email/changes` 四类方法。它把已有的 15 个增量向量回放成可审计 v2 trace，并累计与双 frontier、前缀补位、重建和完整性决策直接相关的计数。

预算、trace 和 metrics 与其他同步、任务、回放或可观测性项目共享一般机制；这里保留它们只是为了证明 JMAP 邮件查询的具体状态转移和 `JmapEmailPrefixCertificate`（兼容 `DecisionCertificate`） 输入，不把它们宣传成通用性能平台、通用日志或通用恢复框架。

```sh
# 在克隆后的仓库根目录执行
python3 scripts/benchmark_metrics.py
PYTHONPATH=src python3 -m unittest tests.test_metrics -v
```

输出位于：

- [metrics.json](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/metrics/metrics.json)：机器可读的运行、fixture SHA-256、能力/限制、每场景指标和 trace 清单；
- [metrics.md](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/metrics/metrics.md)：面向评审的汇总表；
- `outputs/metrics/traces/Cxx.json`：每个向量的逐响应脱敏 trace。

## 指标口径

| 指标 | 口径 |
|---|---|
| `requests_attempted` | 观察到响应事件时对应的请求尝试数，包含随后被 generation 丢弃的响应；仅统计有响应的调用，计划但未发出的调用在 `requests_planned` |
| `requests_planned` | `plan` 事件推导的调用数；按 `maxObjectsInGet` 计算 Email/get 分段数；方法拆分见 `requests_planned_by_method` |
| `responses_accepted` / `responses_dropped` | 进入本地投影的响应和被旧代次丢弃的响应 |
| `objects_received` / `unique_objects_received` | Email/get `list` 中对象数及其 ID 去重数；`notFound` 单独计数 |
| `query_removed` / `query_added` | queryChanges 的删除和插入条目数 |
| `query_fill_requests` | 因前缀缺口发出的同 queryState 补位请求数 |
| `query_rebuilds` | 完整 query 结果或 query history 失效触发的重建数 |
| `email_rebuilds` | Email history 失效触发的新 Email baseline/rebuild 数 |
| `budget_terminations` | `max_rounds` 或 `max_calls` 在向量中阻止后续工作的次数 |
| `response_bytes` | 仅使用 fixture 显式提供的 `response_bytes`/`bytes`；当前向量没有该字段，值为 `null` |

`response_bytes` 缺失时不会使用 JSON 序列化长度补值；脚本也不会测量延迟、吞吐、内存或网络请求。这样可以避免把合成 fixture 的存储成本误报为真实 JMAP payload 成本。

## 场景覆盖

当前固定向量覆盖：属性更新、remove/add 移动、同 queryState 补位、补位 state 不一致、Email/query history 失效、Email history 失效、窗口外新增、超前 Email state、旧 generation 响应、能力/分段限制、调用/轮数预算、空/短/满列表。每个场景都保留 `before`/`after` 状态哈希和 `reason_code`，待取 ID 只保存哈希，可回溯到 `tests/vectors/incremental_cases.json`。

## 证据边界

该基准是 `synthetic-local`，不使用 HTTP、TLS、OAuth 或真实账号；它本身不替代 [真实服务互操作记录模板](interop-record-template.md)，也不产生网络性能承诺。M4 的独立真实证据现已另行保存于 [真实服务验证报告](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E7%9C%9F%E5%AE%9E%E6%9C%8D%E5%8A%A1%E4%BA%92%E6%93%8D%E4%BD%9C%E4%B8%8E%E6%80%A7%E8%83%BD%E9%AA%8C%E8%AF%81-2026-10-26.md) 和对应脱敏 JSON；本页的合成 `response_bytes=null` 与 `performance_claim=false` 仍然只描述这组本地向量。

如需对已授权的真实 JMAP 服务取 RTT、请求/响应字节和四个固定方法的对象/变更计数，使用 [真实 JMAP 服务性能基准](live-performance-benchmark.md)。该入口会在无凭据或非 2xx 时明确输出 `blocked`/`partial`，不会把本地向量升级为网络性能结果。
