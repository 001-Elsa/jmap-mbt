> 版本边界：以下记录针对此前 0.1.x。当前本地未发布 0.2.0 已移除位置证书和本地序列归并；现行行为以 README、state-contract.md 及本轮改造报告为准，旧数量和通过项不自动适用。

# 增量恢复、预算和响应接纳（主功能的安全边界）

本文件描述的是保护 JMAP 邮件查询前缀一致性的内部机制。预算、恢复、generation
和响应接纳本身不是 MoonJMAP 的独立卖点；它们只有在防止双 frontier 被跳过、旧响应
覆盖新视图或未完成前缀被误报 `Ready` 时才有意义。

## 正常增量闭环

一次刷新有两条相互独立的进度链：

1. 使用 `EmailProgress` 发送 `Email/changes`，标记前缀中属性需要重新取得的邮件；
2. 使用 `QueryProgress` 发送 `Email/queryChanges`，先删除 `removed`，再按 `added.index` 升序插入；
3. 对进入前缀、仍在前缀但属性变化的 ID 发送 `Email/get`；
4. 如果前缀长度小于 `min(prefix_limit,total)`，从缺口位置按同一 queryState 补取；
5. 所有响应归位并完成完整性检查后再提交 checkpoint。

补位请求必须能够推进连续前缀：当缓存长度仍小于
`min(prefix_limit,total)` 时，如果服务端返回 `ids=[]`，内核立即返回
`ProtocolFailure`，而不是重复发送同一个 `position`。空页只有在前缀已经达到目标长度
（例如 `total=0` 或剩余结果已耗尽）时才可作为正常响应处理。这样可以把服务端返回的
自相矛盾分页（`total` 声称仍有结果但本页没有任何 ID）与预算耗尽区分开，避免在
`Pending` 状态中无意义地空转。

`removed` 中不在本地缓存的 ID 是合法情况；它表示窗口外或已经被另一条响应处理，不应使整个同步失败。相同 ID 先 remove 后 add 时，以 add 的新 index 为准，并在最终序列中只保留一份。

## 历史失效的独立处理

| 响应 | 失效的进度 | 必须做的事 | 可保留的内容 |
| --- | --- | --- | --- |
| `Email/queryChanges/cannotCalculateChanges` | `QueryProgress` | 重新 `Email/query` 前缀，重新确认 total 和顺序 | 当前 Email 对象属性和 `EmailProgress`（若身份仍相同） |
| `Email/changes/cannotCalculateChanges` | `EmailProgress` | 重新取得当前前缀所需属性；必要时重新 query 协调排序 | 已确认的 query 顺序和 `QueryProgress` |
| `queryChanges/tooManyChanges` | `QueryProgress` | v0.1 直接 query 有界前缀 | 对象缓存（需逐项检查） |
| 窗口对象 `notFound` | 本轮完整性 | 重新 query 或补位，不能留下空洞 Ready | 仍然可验证的 ID 和另一条状态链 |

当 `Email/changes` 历史失效而 `queryState` 仍然有效时，内核会保留该
`queryState`，同时把 `query_required` 置为真。调用方注入新的 Email 基线后，
`begin_resume_with_email_state` 首先发出同一查询的 `Email/queryChanges`，再重新
取得前缀对象；这样对象历史失效期间发生的成员变化或排序变化不会被旧前缀掩盖。
如果查询历史也已经失效，则保留原有的完整 `Email/query` 重建路径。

失效链的 token 不得写入新的 checkpoint。若一个批次同时报告两条历史失效，先记录两个原因，再执行新的 query；不得只恢复其中一条然后假报 Ready。

## 预算

MoonBit `Limits` 为一次刷新设置前缀、响应轮数、响应字节、单次 `Email/get`
对象数和本代 `Email/changes` 变更条目总数：

```json
{"prefix_limit": 50, "max_rounds": 3, "max_bytes": 65536, "max_objects_per_get": 20, "max_changes": 500}
```

`max_rounds` 按已接受的响应次数计数；`max_calls_in_request` 是能力投影中的 wire 批量限制，当前计划每次只产生一个调用，不是刷新预算。预算在接受每个响应后更新，并在提交前检查。预算为零时：

* 已确认的状态和已应用变化保留在 `Pending` checkpoint；
* 未确认响应对应的 token 不推进；
* `ordered_ids` 不得被标为 `Ready`；
* `pending_work` 必须包含剩余方法、基准 state 和请求代次。

持续变化超过 `max_rounds` 时返回 `Pending` 或 `NeedsRefresh`，由调用方决定下一轮；不得用“最后一次响应”掩盖未追赶的变化。

`max_changes` 是独立于轮数和字节的累计上限，按 `Email/changes` 响应中
`created`、`updated`、`destroyed` 三个数组的条目数累加（兼容的
`ChangesData` 则按 `removed + updated`）。跨数组重复 ID 仍按条目计数，避免服务端
通过重叠集合绕过预算；对象获取仍采用 destroyed 优先规则。每个计划把
`maxChanges` 精确设为本代剩余预算，并在 ticket 中绑定同一个值。服务端返回超过
请求值的页面会被判为 `ProtocolFailure`；页面带有 `hasMoreChanges=true` 且累计值达到
上限时保存 `Pending` checkpoint，不再发出下一页请求。checkpoint 保存
`changes_seen`，恢复时不能把已消费的变更计数清零；只有调用方显式提供更大的
`max_changes` 才能继续追赶。

调用 `refresh(view)` 或 `resume_with_email_state(view, state)` 会返回
`RefreshStart { view, plan }`，其中 `view.generation` 已递增。调用方必须把这个新
`view` 和其 `plan` 一起保存，并用新视图接纳后续响应；原视图只能保留为旧缓存，不能
继续接收这一代响应。这样可以把恢复时的旧请求和新请求明确隔离。

## 响应接纳顺序

实现应按下列顺序拒绝危险响应：

1. 校验请求代次、账号、查询身份和期望方法；
2. 校验 JSON 外形和 method-specific 字段；
3. 校验响应状态属于当前基准 state；
4. 应用 changes 或 queryChanges；
5. 对 get 结果按 ID 归位并确认属性集合；
6. 检查补位是否仍使用同一 queryState；
7. 更新预算、待办和完整性；
8. 最后才允许提交 checkpoint。

## 诊断记录

每次 `Pending`/`NeedsRefresh`/`ProtocolFailure` 应记录方法、generation、account/query hash、基准 state、已确认 state、原因代码和剩余预算。记录中不要保存 OAuth、Cookie、完整正文或可识别的个人邮件内容；fixture 只使用合成 ID 和脱敏字段。

