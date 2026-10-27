> 版本边界：以下记录针对此前 0.1.x。当前本地未发布 0.2.0 已移除位置证书和本地序列归并；现行行为以 README、state-contract.md 及本轮改造报告为准，旧数量和通过项不自动适用。

# MoonJMAP 跨实现逐步对拍（内部证据）

`scripts/run_differential.py` 是本项目的跨实现逐步对拍入口。它先由
`scripts/generate_differential_adapter.py` 从
`tests/vectors/incremental_cases.json` 生成 `cmd/differential/main.mbt`，再
执行真实的 MoonBit 程序：

```text
moon run --target wasm cmd/differential
```

这是主功能的验证工具，不是 MoonJMAP 的独立产品定位；它不提供通用 replay、
通用 journal、通用 RPC 或通用状态机框架。生成的 MoonBit 程序只依赖
`src/email` 和 `src/sync` 的公开类型与函数。每
个 vector 事件都转换为一个带 ticket 的 `ServerResponse`，交给
`accept_response`；程序在每一步打印 `M|case|step|...` 状态投影，规划投影
打印为 `P|case|step|plan=...`。Python 运行器独立导入
`examples.replay_vectors.Replay`，按同一 fixture 逐步回放，再比较两边都能
表达的字段：

- 有序前缀 ID；
- 不透明 `queryState` 和 `Email state`；
- generation；
- 下一请求的 method、ID、position 和 limit 投影；
- C15 的 `total` 与返回 ID 数量关系。

报告写入
`outputs/MoonJMAP-跨实现逐步对拍-2026-10-25.json`。运行成功要求 MoonBit
命令成功、所有 trace 行可解析、C01–C15 每个场景的比较均通过：

```sh
# 在克隆后的仓库根目录执行
python3 scripts/run_differential.py
```

## 结果边界

这不是把 Python oracle 当成 MoonBit 的实现，也不是完整跨语言等价证明。两
个实现对“隐式工作”和“预算耗尽”的抽象不同，运行器将这些差异写入报告的
`known_boundaries`，并在比较时只跳过明确列出的字段：

- C01 的 Email 属性变化后，生产内核会先发一个 query reconciliation；向量
  的直接 `Email/get` 由适配器补入确定性的空 `queryChanges` 响应。
- C02/C03/C05 中，生产内核在补位或 Email/get 尚未完成时公开 `Pending`；
  简化 oracle 将部分中间状态保留为 `Ready`。
- C05 的跨 `queryState` 补位会在生产内核中清除不可复用 token；oracle 保
  留 `q1` 作为诊断值。
- C09 的超前 Email/get state 在生产内核中是可恢复的 `Pending`，并产生
  `Email/changes` 计划；oracle 使用 `NeedsRefresh/email_state_gap` 标签。
- C12 的 fixture 用截短列表表现预算耗尽，而生产内核保留有序前缀，把剩余
  ID 放入 `pending_get`；适配器明确输出 fixture 的预算投影，同时仍检查生
  产计划的 `maxObjectsInGet` 分段。
- C14 从已有完整对象的视图开始；适配器用独立的 setup budget 建立该夹具，再施加一轮预算。
  它在 round budget 耗尽后拒绝第二个 delta；oracle 在标记预算失败前仍
  改动了列表，适配器保留生产内核的拒绝语义。
- C15 只比较空列表、短列表和恰好 N 条的长度关系；生产内核尚未取得 Email
  baseline 和对象时保持 `Pending`。

因此 15/15 只表示上述**有界共同投影**逐步一致，并不表示：

- Stalwart v0.16.27 的真实服务互操作记录已经覆盖所有固定只读方法；但本对拍报告本身仍不替代该外部证据，也不扩展为所有 JMAP 服务兼容；
- HTTP、TLS、OAuth、SSE 或网络重连已经验证；
- MoonBit 与 Python 在所有私有字段、所有错误路径、所有输入域上全等价；
- 线性化性能、内存占用或部署行为已经获得保证。

fixture 的 SHA-256、MoonBit 退出码、每个场景的比较字段和边界记录均保留在
机器报告中，便于 fixture 或核心逻辑变化后重新审计。
