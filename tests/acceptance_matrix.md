# MoonJMAP v0.1 独立验收矩阵

这份矩阵对应当前收窄后的主交付：**JMAP 邮件查询视图增量一致性与恢复内核**。`tests/verify.py` 是独立 Python oracle，故意不导入 `src/`，避免“实现自己生成期望值再验证自己”。它验证状态转换和不变量；`src/sync/*_test.mbt` 则直接覆盖 MoonBit 公共 API 的请求票据、响应接纳、预算和恢复边界。JSON 向量回放与 MoonBit 测试是两层独立证据，C01–C15 另有 `scripts/run_differential.py` 逐步对拍，比较范围与适配边界见 `docs/differential-harness.md`，不能扩展成完整等价证明。

运行：

```bash
python3 tests/verify.py
# 所有 src/ 与文档交付齐全后，再运行：
python3 tests/verify.py --strict-structure
```

| 编号 | 场景 | 独立 oracle | 必须观察到的实现行为 | 规划依据 |
| --- | --- | --- | --- | --- |
| 1 | 初次建立，`Email/get` 返回顺序与 query IDs 不同 | `initial_get_order` | 按 ID 归位；顺序仍是 query 顺序；完成对象覆盖才可 Ready | §7.1、§10 初次建立 |
| 2 | 成员/顺序不变但邮件属性变化 | `attribute_update_without_query_delta` | 继续处理 Email/changes；只获取受影响对象；不能因 queryState 不变而跳过；需要查询复核 | 主演示 A、§7.2 |
| 3 | 删除中间项后前缀缺口补位 | `remove_middle_and_fill_gap` | 先 remove，再按同一 queryState 从 position=L 补位；对象拿齐后才能 Ready | 主演示 B、§7.3 |
| 4 | 补位响应 queryState 改变 | `mixed_state_gap_rejected` | 不拼接 q1/q2 两段；返回 NeedsRefresh；不得伪造 Ready | 主演示 B、§7.3 |
| 5 | `Email/queryChanges/cannotCalculateChanges` | `query_history_invalidated` | 仅使查询历史失效；旧 query token 不推进；重取有界前缀 | §6、§7.4 |
| 6 | `Email/changes/cannotCalculateChanges` | `email_history_invalidated` | 仅使 Email 对象进度失效；旧 Email token 不推进；不冒充空列表 | §6、§7.4 |
| 7 | 多页 changes，token 字典序/数值不单调 | `email_changes_pagination_and_opaque_tokens` | 按 oldState 精确相等衔接；使用 hasMore；不比较 token 大小 | §6.2、§10 changes 链 |
| 8 | get 观测到超前 Email state | `get_state_gap_requires_changes` | 不跳过 changes；保留旧 EmailProgress 并安排追赶 | §7.2 第 9 步 |
| 9 | queryChanges `tooManyChanges` | `query_too_many_changes_requires_requery` | 使查询进度失效并重取有界前缀；不推进无效 token | §7.4 |
| 10 | 非法 `added.index` | `invalid_added_index_rejected` | 协议失败；不把越界 index 静默 clamp 后提交 | §7.2、§7.4 |
| 11 | 当前窗口对象 `notFound` | `not_found_is_not_empty_success` | 保留旧列表为过期展示并标记恢复；不能当作本地删除后 Ready | §7.4 |
| 12 | 请求代次切换后旧响应晚到 | `old_generation_cannot_overwrite` | 丢弃旧响应，不能覆盖新查询/新视图 | §6.3、§7.4 |
| 13 | 同 token 在不同账号/查询上下文 | `identity_bound_tokens` | token 与 AccountScope/QueryKey 绑定；不能跨上下文复用 | §5.1、§6 |
| 14 | 预算/多页未完成 | `budget_pending_is_resumable` | 返回 Pending/NeedsRefresh；checkpoint 保存已处理 token 与 pending_work | §7.2、§7.4 |
| 15 | JMAP 响应 callId 重复 | `response_container_preserves_duplicate_call_ids` | 保留响应列表和顺序；不能 callId→单响应覆盖 | §7.4 末段 |
| 16 | malformed response / invalid reference | `malformed_response_and_invalid_reference` | 协议失败不推进任何未经验证的状态；不得用空对象代替失败 | §7.4 |
| 17 | 组合增删/移动、任意添加顺序 | `deterministic_delta_fuzz` | remove 后按 added.index 升序插入；remove→add 不重复；与独立全量列表一致 | §7.2、§10 小规模组合 |
| 18 | 代码边界和发布范围静态检查 | `static_structure`（`run` 自动执行） | 存在 `src/sync`、`src/jmap`、`src/email`、文档矩阵；HTTP/SSE/SMTP/IMAP 等不成为核心模块 | §4、§9、§13 |
| 19 | `Email/changes` 累计条目预算耗尽 | `src/sync/sync_test.mbt` 的 `Email changes plan and checkpoint enforce cumulative maxChanges` | 每页 ticket/request 携带剩余 `maxChanges`；已接受条目写入 `changes_seen`；`hasMoreChanges=true` 且达到上限时返回可恢复 Pending，不继续发页，也不把未追赶历史标成 Ready | §10 changes 链、预算契约 |
| 20 | generation 到达 `Int` 上界 | `src/sync/sync_test.mbt` 的 `generation increment is checked at the Int boundary`、`refresh and resume expose generation overflow as protocol failure` | `@int.MAX_VALUE` 不递增、不回绕；checked API 返回 `ReasonResult`/`ProtocolFailure`；兼容 API 返回原代次的协议失败视图和空计划 | §6.3、§7.4、状态契约 §5 |
| 21 | 固定向量的请求/对象/预算可追溯指标 | `scripts/benchmark_metrics.py` + `tests/test_metrics.py` | 生成 v2 `controls/events/final` trace；请求规划与观察响应分开；按方法统计对象、变更、重建、generation 丢弃和预算终止；缺失 wire bytes 保持 `null`；终态字段与向量 expected 硬校验 | §10 预算、`docs/trace-schema.md` v2 |

## 需要接入 MoonBit 公共 API 的证据

独立 oracle 通过后，还需对实际实现记录：

1. 每个场景输入的已有 `EmailView`/checkpoint、响应夹具和请求票据代次。
2. 产生的下一批 JMAP 方法调用（四种允许方法、顺序、`oldState`、`position`、`limit` 和固定展示属性）。
3. 视图输出的 `ordered_ids`、对象覆盖集合、`queryState`、Email state、`completeness` 和 `pending_work`。
4. 失败时不得推进 token；成功提交必须同时携带视图和 checkpoint。
5. 请求次数、对象获取量、响应字节、重建次数和预算终止原因。固定向量可运行 `python3 scripts/benchmark_metrics.py` 取得合成模型证据；只报告源中可推导或明确测量的值，不把模型结果写成真实服务互操作。

## 明确不在本矩阵中的能力

HTTP/TLS/OAuth/session discovery、SSE、SMTP/IMAP/POP3、MIME、blob、Email/set、完整 JMAP server、通用 JSON/RPC/Patch、数据库事务和真实云邮箱认证。它们在当前规划中属于调用方或明确排除项；添加这些模块会扩大重合面，不能替代同步闭环的验收。

