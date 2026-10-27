# JMAP 有界邮件视图契约

本文定义 MoonJMAP 0.2.0 的可验收贡献。它不是通用增量同步框架，也不是证书、审计或回放平台；每条规则都绑定到 RFC 8621 的 Email 对象和可变查询。

## 输入与输出

输入被限制为一个服务身份、一个 accountId、一个邮箱视图（指定邮箱的最新邮件或未读邮件）和一个前缀上限。核心只接收外部适配器已经解码的四类 JMAP 响应：`Email/query`、`Email/queryChanges`、`Email/get` 和 `Email/changes`。

每次 `plan` 只产生一个请求。调用方执行请求后，把带 accountId、request ticket 和状态边界的响应交回核心。核心输出下一请求、需要刷新、暂缓、协议失败或 Ready 展示结果。

## 三条 JMAP 专用不变量

1. **对象状态和查询状态不能互相冒充。** `Email/changes` 的 `state` 只推进对象属性历史；`Email/queryChanges` 的 `queryState` 只推进查询结果历史。对象响应观察到新 Email state 后，仍须完成相应的 changes/query reconciliation，不能直接发布旧排序中的对象。
2. **受影响位置之后不能本地猜测。** `queryChanges` 的 removed 和 added 只确定可信前缀的截断位置。截断后的 ID、位置和补位对象必须由同一新 queryState 的 `Email/query` 返回；核心不会用本地 survivors、最终 rank 或通用 patch 重新拼接后缀。
3. **可展示对象必须重新满足可变过滤器。** Ready 前，`Email/get` 返回的对象必须仍属于目标邮箱；未读视图还必须不含 `$seen`。如果对象字段更新、notFound、destroyed 或跨状态响应破坏条件，旧字段立即失效并进入补取、重建或刷新。

## 能力降级

`Email/query` 的可选 `canCalculateChanges=false` 不是成功的空结果。它会被记录到当前查询进度，后续计划不得发出非法的 `Email/queryChanges`，而是使用新的完整 `Email/query` 重建有界前缀。该行为是针对 JMAP 查询能力的降级，不是通用状态机的开关。

## 状态边界

- 空或不匹配的 accountId、ticket、generation、state、queryState、请求 ID、added index 和 `notFound` 归属都在响应接纳前拒绝。
- 旧 generation 的响应只被丢弃，不改变当前视图。
- 同一 queryState 下如果响应声称已改变已知结果或 total，核心拒绝该响应，不把矛盾解释成“可继续同步”。
- `Ready` 只代表当前有界前缀、对象属性和两条状态 frontier 满足本契约，不代表整个邮箱的全局原子快照。

## 可复现实验证

当前测试直接覆盖上述规则：

- `src/sync/bound_response_test.mbt`：accountId 绑定、`canCalculateChanges=false` 降级和伪造 ticket；
- `src/sync/prefix_boundary_test.mbt`：同 queryState、total、added index、后缀查询和预算边界；
- `src/sync/mailbox_consistency_test.mbt`：邮箱归属、未读过滤、对象更新和恢复 Ready；
- `src/sync/rank_prefix_test.mbt`：75,140 个有界合法转移，其中 70,952 个实际执行服务器后缀查询；
- `src/jmap/api_test.mbt`：四种固定方法的 wire 负载、`calculateTotal=true`、显式 ID 和请求字段绑定。

这些测试证明当前实现对声明范围的行为，不能证明基础协议或通用状态机是原创，也不能替代不同 JMAP 服务的兼容性验收。

