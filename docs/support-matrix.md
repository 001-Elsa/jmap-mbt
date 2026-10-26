# v0.1 支持矩阵

本文把规划书中的范围收敛为可验收的输入、输出和限制。矩阵描述的是内核的状态转换能力，不是服务器能力声明。

本矩阵按项目主线排序：前缀一致性、双 frontier 协调和邮件查询决策证书是公共交付；能力投影、预算、checkpoint、generation 和 wire 校验是防止错误 `Ready` 的内部支撑。HTTP、TLS、OAuth、SSE、邮件写入和通用查询语言不属于本项目范围，也不会因为出现在相邻 Mooncakes 项目中而被重复实现。

## 查询视图

| 项目 | 支持 | 固定契约 |
| --- | --- | --- |
| 查询 1 | 是 | 指定 `mailboxId`，`receivedAt` 降序，`collapseThreads=false` |
| 查询 2 | 是 | 指定 `mailboxId`，`notKeyword: "$seen"`，`receivedAt` 降序，`collapseThreads=false` |
| 前缀 | 是 | `position=0` 的连续前缀，长度由 `prefix_limit` 限制 |
| 总数 | 是 | 保留 `total`；服务端不提供或格式不符时视为协议失败 |
| 空/短结果 | 是 | `total < prefix_limit` 时以 `Ready` 表示“已确认不足”，不制造缺口 |
| 非零起点 | 否 | 返回 `Unsupported`，不把窗口中间的一段冒充连续前缀 |
| 任意 filter/sort builder | 否 | 调用方先选择固定视图；不在本包扩张通用查询语言 |

## 展示属性

| 属性 | 取得方式 | 缺失行为 |
| --- | --- | --- |
| `id` | `Email/query` 的 ID 加 `Email/get` | 缺失 ID 使本轮 `Pending` 或 `NeedsRefresh` |
| `threadId` | `Email/get` | 缺失字段按协议失败处理 |
| `mailboxIds` | `Email/get` | RFC `Id[Boolean]` 对象；适配器保留每个 key 和 boolean，不能压成 `Array[String]`；字段缺失按协议失败处理 |
| `keywords` | `Email/get` | RFC `String[Boolean]` 对象；适配器保留每个 key 和 boolean；字段缺失按协议失败处理；仅属性变化时重新取得 |
| `receivedAt` | `Email/get` | RFC UTC date-time；以 `Some(String)` 保存；缺失或 `null` 不能标 `Ready`，并按协议失败/补取处理 |
| `subject` | `Email/get` | 以 `Some(String)` 保存；缺失或 `null` 不能标 `Ready` |
| `from` | `Email/get` | RFC `EmailAddress[]`（地址中的 `name` 可为 `null`）；缺失或 `null` 不能标 `Ready` |
| `preview` | `Email/get` | 以 `Some(String)` 保存；缺失或 `null` 不能标 `Ready` |

不读取 `bodyStructure`、正文、附件和 blob；这些字段即使出现在服务器响应中也不进入视图。

### Email/get 到内核投影

对于带有显式 ID 的 `Email/get`，响应必须逐一在 `list` 或 `notFound` 中给出同一
请求 ID；遗漏请求 ID 会被内核判为 `ProtocolFailure`，不会清除已有对象的待取标记
或把旧属性误报为新结果。空 ID 的 `Email/get` 只用于建立账号 Email state 基线。

`src/email.EmailRecord` 是有限的内核投影，不是把 JMAP JSON 原样存储的通用对象。外部适配器应按下面规则构造它：

* `mailboxIds` 和 `keywords` 是 JSON 对象（例如 `{"mbox-inbox": true}`），分别转换为 `Array[BooleanEntry]?`；`BooleanEntry` 同时保存 key 和 value，v0.1 要求 value 为 `true`（false 会保留在结构中供诊断，但不能通过完整性检查）。`Some([])` 表示服务器明确返回空对象，`None` 表示缺失或 null，不能只保留 key，也不能把对象误读为 JSON 数组。
* `from` 是地址对象数组（例如 `[{"email":"a@example.test","name":"Alice"}]`），转换为 `Array[EmailAddress]?`。`EmailAddress.name` 的 `None` 表示该地址没有 name；它不是把缺失 name 伪造为 `""`。
* `receivedAt`、`subject`、`preview` 和 `from` 使用 Option 是为了让解码层保留“未提供/为 null”的事实。v0.1 的 Ready 契约要求这些展示字段为 `Some(...)`；`None` 只能导致补取、Pending 或 ProtocolFailure，不能被 `EmailRecord::empty` 的默认值掩盖。
* `EmailRecord::is_complete` 是提交前的结构检查。明确返回的空 mailbox/keyword 映射（`Some([])`）本身可以是合法值，但 `None` 不能当作空映射；key 不能为空或重复，地址的 `email` 不能为空，`receivedAt` 不能是空字符串，`id`、`threadId` 和上述展示字段必须存在。

适配器可以在解码阶段直接把缺失/null 的必需字段报告为 ProtocolFailure；如果为了保留诊断上下文而构造了带 `None` 的 `EmailRecord`，同步核心会把它视为未完成的取数义务，继续 Pending/补取，且绝不会提交 Ready。两条路径都禁止用空字符串或空数组把缺失字段伪装成完整对象。

## JMAP 方法

邮件对象变化只使用 `EmailChangesData` 的 RFC 三数组：`created`、`updated`、`destroyed`，分页字段为 `has_more_changes`。早期 `ChangesData`、`ChangesResponseEnvelope` 和两个响应枚举的 `ChangesResult` 入口已移除；调用方应构造 `EmailChangesResult`。`QueryChangesData` 的 `removed/added` 属于另一条查询顺序链，按 RFC 保留。

| 方法 | 用途 | 状态推进 |
| --- | --- | --- |
| `Email/query` | 首次建立或查询历史失效后的有界前缀 | 产生新的 `queryState` 和有序 ID |
| `Email/queryChanges` | 追赶查询成员、顺序、total 的变化 | 只推进 `QueryProgress` |
| `Email/get` | 取得前缀中邮件的展示属性 | 观察到的 `state` 不可跳过 `Email/changes` |
| `Email/changes` | 追赶账号内邮件对象变化 | 只推进 `EmailProgress` |

`Email/query` 请求固定带 `calculateTotal=true`。`total` 决定目标前缀长度，因而缺失、为
`false` 或解码为非整数的总数都不能被当作一个可提交的 v0.1 查询结果；Python wire
适配器会拒绝不满足这一固定契约的请求和响应输入。

### 计划到 wire 的固定投影

`src/sync` 的 `Request.filter` 和 `Request.sort` 是 `src/email` 中的封闭类型，
只表达这两种固定视图；它们不是可直接发送的 JSON，也不是通用筛选器构造器。
外部 JMAP 适配器必须按下面的固定映射生成 RFC 8621 参数：

```json
// ViewSpec::Latest(mailboxId)
{"inMailbox": "mailboxId"}

// ViewSpec::Unread(mailboxId)
{
  "operator": "AND",
  "conditions": [
    {"inMailbox": "mailboxId"},
    {"notKeyword": "$seen"}
  ]
}

// 两种视图共有的 sort
[{"property": "receivedAt", "isAscending": false}]
```

`ViewSpec::filter()`、`ViewSpec::sort()` 返回的字符串只用于查询身份的可读
canonical/debug 表示；适配器不得把 `inMailbox:...` 或 `receivedAt:desc`
直接放进 JMAP `filter`/`sort` 字段。

以下方法在 v0.1 返回 `Unsupported` 或由调用方自行处理：`Email/set`、`EmailSubmission/*`、`Thread/*`、`Mailbox/*`、SSE、Session、上传/下载和所有非 Email 资源。

## 服务器能力和限制投影

内核只接受调用方投影后的限制；不发起 Session 发现。调用方至少应提供：

```json
{
  "maxCallsInRequest": 1,
  "maxObjectsInGet": 50,
  "supportsFilter": true,
  "supportsSort": true,
  "supportsQueryChanges": true,
  "supportsEmailChanges": true,
  "supportsResultReference": false
}
```

`maxCallsInRequest=1` 时，`query`、`get`、`changes` 必须拆成独立计划；不得假设跨请求的 `ResultReference` 仍然有效。`maxObjectsInGet < prefix_limit` 时分段计划，预算耗尽则返回 `Pending`，而不是提前报告 `Ready`。内核另外要求 `Limits.max_changes > 0`；每个 `Email/changes` 计划把 wire `maxChanges` 设为本代剩余条目预算，并在 checkpoint 的 `changes_seen` 中累计 `created + updated + destroyed`。分页响应在预算耗尽时保留新 state 和已应用变化，但不发出下一页计划，除非恢复时提高 `max_changes`。

MoonBit 调用方应把上面的记录转换为 `CapabilityProjection`，并优先调用
`open_view_with_capabilities(...)`。该入口会在建立视图前拒绝不支持固定
filter/sort、`Email/queryChanges` 或 `Email/changes` 的服务，以及非正的能力
限制；旧的 `open_view(...)` 只保留默认能力投影的本地便捷入口。能力投影不包含
Session URL、凭据或传输句柄。

## 输出状态

| 输出 | 可提交 `ordered_ids` | 可推进 token | 典型原因 |
| --- | --- | --- | --- |
| `Ready` | 是 | 是 | 前缀和属性完整、两条链无待办 |
| `Pending` | 否（保存中间进度） | 仅推进已确认响应 | 调用/字节/轮数预算耗尽，等待下一次继续 |
| `NeedsRefresh` | 否 | 对失效链不推进 | `cannotCalculateChanges`、同批 queryState 不一致、窗口对象丢失 |
| `Unsupported` | 否 | 否 | 服务器不支持固定 filter/sort 或能力不足 |
| `ProtocolFailure` | 否 | 否 | 响应缺失、类型不符、状态或代次错配 |

## 不纳入 v0.1 的实现项

HTTP/TLS/OAuth、SSE 自动重连、通用 JSON/RPC、IMAP/POP3/SMTP、MIME、数据库事务、全文索引和 UI 都由调用方或其他包提供。它们不是本项目的差异化交付。

## 主功能与内部支撑的边界

| 层次 | 交付内容 | 对外叙事 |
| --- | --- | --- |
| 主功能 | 固定 JMAP 查询、Email/queryChanges 与 Email/changes 的双 frontier、ordered prefix 补位、Email/get 按 ID 归位 | 这是 MoonJMAP 要解决的工程问题 |
| 主功能扩展 | `JmapEmailPrefixCertificate`（兼容 `DecisionCertificate`）及其纯 MoonBit verifier | 这是面向 JMAP 邮件前缀的可解释、可重放证据 |
| 内部安全机制 | generation、预算、checkpoint、Pending/NeedsRefresh、账号绑定响应 | 只证明主功能不会跳过历史、接受旧响应或假报 Ready |
| 测试/交付证据 | Python wire、oracle、trace、metrics、差分 harness、归档 smoke | 只用于复现和审计，不宣称通用工具能力或线上性能 |

