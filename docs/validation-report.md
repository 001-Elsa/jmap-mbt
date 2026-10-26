# 验收矩阵与证据记录

本页定义可重复的本地验收方法。当前向量和回放不等于真实服务器互操作；后者已在 [互操作记录模板](interop-record-template.md) 的基础上形成 [Stalwart v0.16.27 真实服务验证报告](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E7%9C%9F%E5%AE%9E%E6%9C%8D%E5%8A%A1%E4%BA%92%E6%93%8D%E4%BD%9C%E4%B8%8E%E6%80%A7%E8%83%BD%E9%AA%8C%E8%AF%81-2026-10-26.md)。

验收顺序按项目主线解释：先看 JMAP 邮件查询的双 frontier、有序前缀补位、对象 ID 归位和完整性门禁，再看 `JmapEmailPrefixCertificate`（兼容 API 名 `DecisionCertificate`） 是否能复核同一状态转移。预算、checkpoint、wire、trace 和对拍通过只说明这些主功能有安全边界和可复现证据，不把项目扩大为通用同步、通用 RPC 或完整邮件客户端。

## 三层证据

| 层级 | 输入 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| RFC 对照向量 | `tests/vectors/rfc8621_vectors.json` | 固定请求、响应字段和状态解释 | 服务器实现、网络、认证 |
| 变化组合回放 | `tests/vectors/incremental_cases.json` | 变化应用、补位、失效和代次规则在模型中一致 | MoonBit 编译器所有目标、真实时序 |
| 真实服务记录 | 由调用方保存的脱敏原始响应 | 某版本服务支持矩阵和实际响应形状 | 其他服务、未来版本、性能保证 |

## 必须通过的核心场景

| ID | 场景 | 期望结果 |
| --- | --- | --- |
| C01 | 顺序不变但 `keywords` 变化 | 重新 get 变化 ID，顺序不变，最终 Ready |
| C02 | 前缀中间成员移除 | 先删除、同 queryState 补位，得到连续前缀 |
| C03 | 同 ID remove 后 add | 以新 index 为准，最终无重复 |
| C04 | removed 含窗口外 ID | 忽略该删除，仍可 Ready |
| C05 | 补位 queryState 改变 | 拒绝混接，NeedsRefresh/requery |
| C06 | Email history 失效 | 只重建对象进度，不误使 queryState 失效 |
| C07 | Query history 失效 | 重 query 前缀，可保留有效 EmailProgress |
| C08 | 窗口外新邮件进入筛选 | 继续追赶，未确认前不能 Ready |
| C09 | get state 超前 | 安排 Email/changes，不能跳过中间变化 |
| C10 | 旧 generation 响应晚到 | 丢弃，不能覆盖当前查询 |
| C11 | `maxCallsInRequest=1` | 拆分请求，不跨请求假设 ResultReference |
| C12 | `maxObjectsInGet < prefix_limit` | 分段或 Pending，不假报 Ready |
| C13 | 不支持固定 filter/sort | Unsupported，不改成本地搜索 |
| C14 | 预算耗尽/持续变化 | Pending 或 NeedsRefresh，保留待办 |
| C15 | 空、短、恰好 N 条 | 正确确认长度，不制造缺口 |
| C16 | `Email/changes` 多页达到 `max_changes` | 每页请求绑定剩余 `maxChanges`，累计 `changes_seen` 写入 checkpoint；带 `hasMoreChanges` 时返回可恢复 Pending，不继续请求并不报告 Ready |

## 本地重放命令

```sh
python3 examples/replay_vectors.py
```

脚本输出每个向量的 PASS/FAIL、最终 ID、完整性状态和诊断原因。执行时应记录 Python 版本和 fixture SHA-256；不要把“脚本通过”改写成“真实服务器已兼容”。

仓库另有不读取实现源码的独立状态机 oracle：

```sh
python3 tests/verify.py
```

它当前覆盖 17 个状态不变量和小规模增删移动 fuzz；`examples/replay_vectors.py` 则逐项回放本页列出的 15 个语言无关向量。两者都属于本地模型证据，不能替代 MoonBit 目标构建或真实服务记录。

`python/moonjmap` 目录中的 Python 模型早于当前 v0.1 契约，仅保留给旧本地脚本迁移使用；它不属于公共 API、wire adapter 或验收证据。当前独立状态机验收唯一以 `tests/verify.py` 为准，MoonBit 交付以 `src/email`、`src/jmap` 和 `src/sync` 为准。

## 当前证据状态

* RFC 语义和边界场景：夹具已提交；核心包已有独立 MoonBit 测试。另有
  `python3 scripts/run_differential.py` 驱动真实 `moon run --target wasm
  cmd/differential`，对 C01–C15 做逐事件共同投影对拍，当前 15/15 通过；
  该结果仍受 `docs/differential-harness.md` 中的已知抽象边界约束，不能升级
  为全实现等价或真实服务互操作结论。
* MoonBit 静态检查：`/Users/hanzhen09/.moon/bin/moon check --target native`、`--target js`、`--target wasm-gc` 均返回 rc0、0 errors（本次 warning 数量见机器可读报告，可能随源码/编译器版本变化）。
* Python JMAP wire 与真实探针 harness 回归：`PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'` 当前 26/26 通过，覆盖固定四方法的 RFC 三元组、结果引用、过滤器、响应顺序、固定数组和 JSON 对象键的严格性、malformed 输入边界，以及真实探针的字节/RTT/脱敏与失败分支。
* MoonBit 目标测试的直接结果使用 `/Users/hanzhen09/.moon/bin/moon` 和当前系统 `PATH`：`moon test --target wasm` 与 `moon test --target wasm-gc` 各 47/47 通过；`moon test --target js` 未能启动，原因是当前 `PATH` 没有 `node`（进程启动返回 `No such file or directory`）；`moon test --target native` 未完成，原因是本机 macOS SDK 的 `.tbd` 文件触发 linker `tapi error: malformed file` / `unknown architecture arm64e.x1-*`。同一报告另外显式使用 Codex bundled Node `/Users/hanzhen09/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node` 运行 JS，结果为 47/47；这项结果单独标记，不能改写成系统 PATH 直跑通过。Python 回放是独立 oracle，不合并计算为 MoonBit 测试覆盖率。
* 真实 JMAP 服务：已取得并脱敏保存 Stalwart Server v0.16.27 的真实响应，覆盖 Session、`Email/query`、`Email/get`、`Email/changes` 和 `Email/queryChanges`；非空 Email 对象证据见 [真实服务验证报告](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E7%9C%9F%E5%AE%9E%E6%9C%8D%E5%8A%A1%E4%BA%92%E6%93%8D%E4%BD%9C%E4%B8%8E%E6%80%A7%E8%83%BD%E9%AA%8C%E8%AF%81-2026-10-26.md) 及 `outputs/real-interop-stalwart-v0.16.27/record-seeded-object-level-20261026.json`。`record-complete-20261026.json` 是较早的空邮箱探针记录。该证据只覆盖记录的 Stalwart 版本、只读方法和本机临时部署，不扩展为所有服务或写操作兼容。
* 性能：已完成同一 Stalwart 实例、5 封合成邮件、5 轮固定只读序列的真实性能基准；20/20 请求返回 2xx。完整指标见 `outputs/real-benchmark/stalwart-local-real-20261026-seeded.json`。这些数据是 loopback 工程基准，不是公网吞吐、容量或生产 SLO。
* Email/changes 变更预算：MoonBit 计划和状态机已实现独立的 `Limits.max_changes`，并
  在 `Request.max_changes`、`RequestTicket.max_changes` 与 `Checkpoint.changes_seen`
  间保持一致；本地边界测试覆盖预算耗尽和恢复计数保留。该预算不等同于真实服务的
  性能上限；本轮 Stalwart 真实运行的 `Email/changes` 是无变化分支，非空多页
  changes 预算仍属于本地边界和待授权的后续服务场景。
* generation 溢出：`checked_next_generation` 拒绝负值和 `@int.MAX_VALUE`，两个
  checked refresh/resume API 返回带 `ProtocolFailure` 视图的 `ReasonResult`；兼容
  refresh/resume API 在同一边界返回原代次、协议失败和空计划，避免旧响应 fence 回绕。

