# 状态、查询身份和 checkpoint 契约（邮件前缀主线的内部安全契约）

这里的状态机、checkpoint 和 generation 只服务于 MoonJMAP 的 JMAP 邮件查询前缀。
它们不是通用同步、通用事件日志或工作流抽象；评审重点应放在两条 frontier 如何共同
决定 `Ready`、如何触发同-state 补位和如何为 `JmapEmailPrefixCertificate`（兼容 `DecisionCertificate`） 提供可验证边界。

## 1. 身份不可混用

每个视图都必须带有完整的账号和查询身份。字符串 token 只在其所属身份内有意义：

```text
AccountScope = service_identity + account_id
QueryKey     = AccountScope + fixed_filter + fixed_sort + collapse_threads
```

`EmailProgress` 的 token 属于 `AccountScope`；`QueryProgress` 的 token 属于 `QueryKey`。实现不得通过比较 token 字典序、长度或版本号判断新旧，也不得把 queryState 当成 Email state。

证书和请求接纳直接比较结构化身份。`QueryKey::canonical()` 只用于诊断显示；它的字符串表示及任何外层日志摘要都不参与身份授权或证书验证。

## 2. 可提交视图

`EmailView` 的最小持久化结构如下：

```json
{
  "account_scope": {"service_identity": "example.test", "account_id": "u1"},
  "query_key": {
    "mailbox_id": "mbox-inbox",
    "filter": {
      "operator": "AND",
      "conditions": [
        {"inMailbox": "mbox-inbox"},
        {"notKeyword": "$seen"}
      ]
    },
    "sort": [{"property": "receivedAt", "isAscending": false}],
    "collapse_threads": false
  },
  "prefix_limit": 3,
  "limits": {
    "max_rounds": 8,
    "max_bytes": 4000000,
    "max_objects_per_get": 50,
    "max_changes": 500
  },
  "ordered_ids": ["a", "b", "c"],
  "total": 12,
  "objects": {
    "a": {
      "id": "a",
      "threadId": "thread-a",
      "mailboxIds": [{"key": "mbox-inbox", "value": true}],
      "keywords": [{"key": "$seen", "value": true}],
      "receivedAt": "2026-10-25T00:00:00Z",
      "subject": "...",
      "from": [{"email": "sender@example.test", "name": null}],
      "preview": "..."
    }
  },
  "email_progress": {"state": "e7"},
  "query_progress": {"state": "q7"},
  "completeness": "Ready",
  "pending_work": []
}
```

`objects` 只包含展示字段，不能被解释为完整邮件对象。示例中的 `mailboxIds` 和 `keywords` 是为了表达 RFC 的对象映射而采用的键值条目投影，不是 JMAP 线协议数组；适配器必须保留每个 key 及其 boolean，v0.1 完整性检查要求这些 membership value 为 `true`。内核中 `Some([])` 表示明确返回的空对象，`None` 表示缺失或 null，二者不能混淆。`from` 保留地址对象数组，地址的 `name` 可以为 `null`。`receivedAt`、`subject`、`from`、`preview` 在内核中保留为 Option，以便识别缺失或 null；`Ready` 只允许 `EmailRecord::is_complete` 为真的对象，不能用空字符串或空数组掩盖缺失字段。`ordered_ids` 必须是服务器返回的顺序；服务器 `Email/get` 的返回顺序不可靠，必须按 `id` 归位。

## 3. Ready 判定

只有同时满足以下条件才允许写入 `Ready` checkpoint：

1. `ordered_ids.length == min(prefix_limit, total)`；
2. 所有前缀 ID 都有完整展示属性；
3. `query_progress` 和 `email_progress` 属于当前 `AccountScope`/`QueryKey`；
4. queryChanges 的 removed/added/moved 已全部应用，删除造成的缺口已按相同 queryState 补位；
5. Email changes 报告的对象变化已取得并归位，或明确证明不影响当前视图；
6. 没有待追赶标志、预算中断、未确认的 `notFound` 或未消费的响应；
7. 最后一个响应的请求代次等于当前视图代次。

`Ready` 只表示这一批响应构成了一个自洽的有界前缀，不承诺服务器不会在下一刻变化，也不承诺多请求读到了全局原子快照。

当前 MoonBit `Checkpoint` 保存账号、查询、能力投影、代次、状态 token、对象、待办
ID 和当前代已接受的 `changes_seen`；`Limits` 由调用方在
`restore_checkpoint(saved, limits)` 时重新提供。恢复方必须
传入与原视图相同或更严格的限制，并让实现再次将 `max_objects_per_get` 限制在已保存
能力上；不能用更宽的限制绕过服务端的批量上限。`changes_seen` 不能高于恢复调用方
提供的 `max_changes`，并且恢复后的下一页 `Email/changes` 会把剩余值编码为
`Request.max_changes`/`RequestTicket.max_changes`。`email_valid`/`query_valid` 由恢复时
是否保存了对应 token 推导，不是可由持久化层单独篡改的授权位；`*_required=true`
表示该有效基线仍有待追赶工作（例如分页 changes 或 queryChanges），不表示 token
已经失效。状态失效时 checkpoint builder 会先省略对应 token，因此恢复仍能区分
“有效但待追赶”和“不可复用”。
如果把 checkpoint 编码成磁盘或网络格式，外层应增加自己的 `format_version` 和
查询/能力版本；本包当前只定义内存结构和恢复校验，不承诺跨版本的二进制兼容。

## 4. Pending 和 NeedsRefresh

* `Pending` 保存已经确认的 token、已应用的局部变化和剩余工作。调用方可在同一身份下继续执行。
* `NeedsRefresh` 丢弃失效链的 token，但保留仍然有效的另一条链和诊断原因。调用方应按计划重新 query 或重新 get。
* `ProtocolFailure` 不推进任何 token；调用方应记录原始响应（脱敏）以便诊断。

## 5. 请求代次

每个计划带有单调递增的 `generation` 和期望响应类型：

```json
{
  "generation": 4,
  "account_scope": "example.test/u1",
  "query_key": {"service_identity": "example.test", "account_id": "u1", "mailbox_id": "mbox-inbox", "view": "Unread"},
  "expects": "Email/queryChanges",
  "base_query_state": "q7"
}
```

如果调用方切换账号或查询，旧计划的响应即使格式正确也必须丢弃，不能覆盖新视图。generation 溢出时应返回协议失败，不能回到 0 造成旧响应重新生效。

`refresh(view)` 和 `resume_with_email_state(view, state)` 返回带有新代次视图的
`RefreshStart { view, plan }`。调用方必须使用返回的 `view` 接纳 `plan` 对应的响应，
不能继续把响应交给发起恢复前的旧视图。

MoonBit `Int` 在本项目支持的目标上是有符号 32 位整数，并且算术在边界处回绕。
内核因此通过 `checked_next_generation` 在递增前拒绝负值和 `@int.MAX_VALUE`；
`begin_refresh_checked` 与 `begin_resume_with_email_state_checked` 返回
`Result[RefreshStart, ReasonResult]`，溢出分支的 `ReasonResult.view.completeness`
为 `ProtocolFailure`，原始代次保持不变。兼容旧 API 的 `begin_refresh` 和
`begin_resume_with_email_state` 也经过同一检查：它们无法改变返回类型，因而在错误时
返回保持原代次的协议失败视图和空计划，而不是让 generation 回绕。调用方应优先使用
带 `_checked` 后缀的 API，以便把这个错误作为不可忽略的控制流处理。

