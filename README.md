# MoonJMAP

**当前工作区为本地未发布的 0.2.0。** Mooncakes 上的 [`001-Elsa/moonjmap@0.1.1`](https://mooncakes.io/docs/001-Elsa/moonjmap) 和远端仓库现有版本仍是历史版本，不能用安装 0.1.1 代替下面的新行为。此轮没有发布、推送或提交赛事。

MoonJMAP 接收调用方取得的 JMAP 响应，维护指定邮箱“最新邮件”或“未读邮件”的前 N 条结果。输出下一条明确请求、需要刷新的状态，或可展示的有序邮件。核心不连接网络，不实现邮件发送、MIME、归档或通用集合复制。

## 当前实现

1. **固定视图条件。** 完整的 `Email/get` 对象也必须仍在指定邮箱；未读视图还必须不含 `$seen`。两条状态链完成后发现矛盾会要求重建查询，不能提交错误 `Ready`。恢复 Ready 快照也检查该条件。
2. **窗口内字段失效。** `Email/changes` 报告窗口内 ID 更新时立即删除旧字段，保留查询位置直到查询链确认。窗口外更新或创建不会直接成为对象缓存或 `Email/get` 请求。
3. **服务器确认后缀。** `Email/queryChanges` 只决定哪个开头仍能保留；不在本地执行 remove/insert/move 或重建结果。首个受影响位置及其后缀由 `Email/query` 在同一新 `queryState` 下重新取得。补位跨状态会刷新。
4. **展示出口。** `committed_emails(view)` 只接纳仍满足 Ready 契约的视图，按查询顺序返回邮件，并复制内部可变集合。Pending/失效状态没有可提交的展示快照。

这比本地差异归并多一次服务器查询，可能重取被截断后缀中的对象。它只减少这份实现的通用重建面，不构成新算法或全局原子快照证明。

## 本地运行

需要 MoonBit 工具链。根目录执行：

```sh
moon check --target wasm --deny-warn
moon test --target wasm --deny-warn
moon run cmd/demo --target wasm
python3 scripts/run_differential.py
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
```

测试覆盖固定视图竞态、对象失效、同状态补位、旧代次与预算边界。`rank_prefix_test.mbt` 用完整服务器新旧列表及所有可保留公共子序列构造合法变化，检查 75,140 种转移；其中 70,952 种实际执行合成后缀查询。对拍保留 15 个有界场景，报告中列出旧向量与新后缀协议的中间状态差别。另可运行 `python3 scripts/run_real_mutation_scenario.py`，在临时本机 Stalwart 上复现 5 封邮件的真实四方法突变记录；脱敏结果见 [mutation-scenario.md](outputs/real-interop-stalwart-v0.16.27/mutation-scenario.md)。

## 使用核心包

本地消费方导入 `001-Elsa/moonjmap/src/email` 与 `001-Elsa/moonjmap/src/sync`。从 `open_view` 和 `plan` 取得请求，由外部适配器执行；实际 wire 响应使用 `accept_bound_response` 保留 accountId。只有 `Commit` 后调用 `committed_emails` 展示结果。状态 token 仅比较相等，不排序，也不跨账号或查询复用。

## 0.2.0 兼容性变化

删除 `DecisionCertificate` / `JmapEmailPrefixCertificate`、逐位置来源槽、任意 before/after 构造器和独立 verifier。旧证书 API 没有新别名或替代“证明平台”。需要展示数据的调用方改用 `committed_emails`。本地序列重建也已移除；调用方必须执行新返回的同状态后缀查询。

`Checkpoint` 只保存当前有界同步义务；预算、generation、两条状态链和完整性门禁是必要的基础机制，不作为独占创新。详见 [状态契约](docs/state-contract.md)、[支持范围](docs/support-matrix.md)、[迁移说明](docs/decision-certificates.md)。

评审需要看本期实质贡献时，优先阅读 [JMAP 有界邮件视图契约](docs/jmap-bounded-view-contract.md) 和 [2026 年 10 月本期实质贡献记录](docs/contest-period-contribution-2026-10.md)。前者把可变邮箱/未读过滤、两条 state frontier、服务器确认后缀和能力降级写成可运行的 JMAP 专用不变量，后者逐项列出当前相对 0.1.1 的源码变化、验证结果和导入历史限制。

## 相似性和来源

邮件协议、集合差异、CDC、增量恢复、前缀截断、版本一致读取和验证都有其他项目或规范先例。此次缩减不等于零相似。[RFC 8621 §4.10](https://www.rfc-editor.org/rfc/rfc8621.html#section-4.10) 已定义对象/查询双状态客户端流程；不得把调用四个方法或双状态组合宣传成发明。

每项改动后重新取得官方完整目录，对当前核心与每个发布包做静态代码比较；精确版本及整包 SHA 一致时才复用固定功能特征证据。候选语义核读与代码词法结果分别记录。不能把扫描覆盖率当赛事通过率。历史报告只描述其各自快照。

[源码来源](docs/source-provenance.md)记录 RFC、标准库、合成夹具与 AI 辅助范围。[仓库导入说明](docs/repository-import.md)说明原有 20 次提交是快照导入，不能当连续开发历史。许可证为 Apache-2.0。0.1.1 的 [发布记录](docs/mooncakes-release-0.1.1.md)及此前实服记录保留历史含义。

## 固定 wire 请求与 total

`jmap.encode_planned_request(request, call_id)` 从核心 Plan 的一条请求生成固定四方法的 JSON envelope，检查结构化查询、账号、ticket 和负载一致。Email/query 与 Email/queryChanges 显式发送 calculateTotal=true，因为核心前缀覆盖检查需要 total。Python EmailQueryChangesRequest 与探针也提供显式 calculate_total 选项；省略时仍遵循 RFC 默认 false。

两种视图的邮箱/未读筛选均含可变属性，RFC 8620 §5.6 规定此时忽略 upToId，因此当前编码器不把该参数宣传为流量边界，也不发送它。双状态流程、calculateTotal 和上述语义都属于标准要求，不是原创贡献。
