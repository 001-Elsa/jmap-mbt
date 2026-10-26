# MoonJMAP：JMAP 邮件查询前缀一致性与决策证书内核

版本：v0.1 实现对照稿（由 2026 年 10 月 25 日规划稿更新）  
规划日期：2026 年 10 月 25 日  
项目状态：核心本地实现、跨实现有界对拍、Mooncakes 公开全量复核、本地源代码交付门禁，以及 Stalwart v0.16.27 真实实现的非空 Email 对象只读互操作与本机性能基准已完成；公开注册表发布和赛事认定仍未完成。本文件保留原规划边界，实际证据以 `docs/validation-report.md`、`docs/differential-harness.md`、`outputs/MoonJMAP-本地向量验收报告-2026-10-25.md` 和 `outputs/MoonJMAP-真实服务互操作与性能验证-2026-10-26.md` 为准。

## 一、项目结论

MoonJMAP 不应继续定位为“MoonBit 的完整 JMAP 客户端”或“邮件协议工具包”。这两种定位都会和 Mooncakes 中已有的 HTTP、IMAP、POP3、SMTP、MIME、邮件模型、JSON-RPC、SSE 和 JSON 工具发生较多重合。

建议把项目收窄为：

> **一个只负责维护 JMAP 邮件查询视图的增量一致性与恢复内核。**

它不负责连接服务器，也不负责发送邮件、解析 MIME、管理附件、实现通用 JSON 或提供完整 JMAP 协议。调用方把服务器响应交给内核，内核判断：

1. 当前缓存的有序邮件列表是否仍然有效；
2. 哪些邮件属性必须重新获取；
3. 列表缺口如何补位；
4. 查询变化和邮件对象变化是否需要再次协调；
5. 当前是否可以安全提交新的视图和 checkpoint；
6. 如果历史失效或预算耗尽，下一步应该怎样恢复。

这个定位不能保证绝对原创，但比“通用 JMAP 客户端”明显更窄、更专门，也更容易和 Mooncakes 中已有项目拉开距离。

## 二、要解决的具体问题

应用通常只缓存邮件列表前 N 条，例如收件箱前 50 封邮件。服务器上可能同时发生两类变化：

- 某封邮件的 `keywords`、主题、发件人或预览发生变化，但它仍然排在原位置；
- 某封邮件进入、离开或移动到查询结果中，导致有序列表发生变化。

JMAP 分别通过 `Email/changes` 和 `Email/queryChanges` 表达这两类变化。单独使用其中一个方法都不够：

- 只处理 `Email/changes`，无法可靠知道邮件在查询结果中的新位置；
- 只处理 `Email/queryChanges`，会漏掉列表成员和顺序不变时的邮件属性更新；
- 删除前缀中的中间邮件后，如果不补取未知尾部，应用会得到少一行的假完整列表；
- 查询历史或 Email 历史失效后，继续沿用旧 token 会把不完整数据误报为已同步。

MoonJMAP 的核心任务就是把这两条状态链协调为一个有明确完整性含义的邮件视图。

## 三、差异化原则

### 3.1 只保留一个主交付

主交付必须是：

```text
已有 EmailView + JMAP 响应
        -> 新的有序邮件视图
        -> 下一批明确的 JMAP 请求
        -> 可恢复的 checkpoint 或未完成状态
```

如果某项功能不能直接帮助完成这个转换，就不进入 v0.1。

### 3.2 所有通用能力都不自研

以下能力全部通过调用方或外部依赖提供：

- HTTP 客户端；
- TLS、OAuth、Session 发现；
- SSE、WebSocket、推送连接；
- 通用 JSON 编解码器；
- 通用 JSON Pointer、JSON Patch、Merge Patch；
- 通用 RPC dispatcher；
- Fake HTTP server；
- 邮件发送、SMTP、IMAP、POP3；
- MIME、附件、正文、加密、签名；
- 数据库、事务和持久化存储。

这样做既减少重复，也让项目的公共 API 集中在 JMAP 邮件视图同步这一件事上。

### 3.3 不把标准内容包装成原创

JMAP 的 `Email/query`、`Email/queryChanges`、`Email/get`、`Email/changes`、ResultReference 和状态 token 来自 RFC 8620/8621。项目不宣称发明这些协议能力。

项目可以主张的范围是：

- 这些标准语义在 MoonBit 中的专用状态表示；
- 两类增量变化的协调算法；
- 有界前缀的补位和完整性检查；
- 失效恢复和预算终止的确定行为；
- 防止旧响应覆盖新视图的请求代次机制；
- 能被独立测试和复现的同步计划。

## 四、产品边界

### 4.1 v0.1 支持范围

一个实例只维护一个账号中的一个只读 Email 查询视图，缓存从位置 0 开始的连续前缀。

支持两种固定视图：

1. 指定 Mailbox 中按 `receivedAt` 降序排列的最新邮件；
2. 指定 Mailbox 中排除 `$seen` 的未读邮件。

支持的展示字段限定为：

```text
id
threadId
mailboxIds
keywords
receivedAt
subject
from
preview
```

支持的 JMAP 方法限定为：

```text
Email/query
Email/queryChanges
Email/get
Email/changes
```

### 4.2 明确不做的内容

v0.1 不实现：

- `Email/set`、写入、删除、移动和草稿；
- EmailSubmission、SMTP、IMAP、POP3、MIME；
- 正文、附件、blob、bodyStructure；
- Thread/get、Thread/changes 以外的线程产品；
- 通用搜索表达式 builder；
- 通用 JMAP Core 客户端；
- 通用请求调度器和 RPC 框架；
- SSE、EventSource、自动重连；
- OAuth、网络发现和服务器能力发现；
- 完整邮箱镜像、邮件备份和本地全文索引；
- 通用 workflow、replay、journal、mock server；
- UI、Web 门户和报告系统。

## 五、核心概念和状态模型

### 5.1 查询身份

查询 token 不能脱离上下文使用。定义：

```text
AccountScope = service_identity + account_id
QueryKey = AccountScope + filter + sort + collapse_threads
```

同一个字符串如果来自不同账号、不同查询或不同状态类型，也不能互相替换。

### 5.2 两条独立进度

```text
EmailProgress
  = AccountScope + 已处理到的 Email 类型 state

QueryProgress
  = QueryKey + 已处理到的 queryState
```

`EmailProgress` 说明库已经处理了账号内 Email 对象变化；`QueryProgress` 说明库已经处理了某个查询结果顺序变化。两者不能混为一个版本号，也不能比较 token 的大小。

### 5.3 邮件视图

```text
EmailView = {
  account_scope,
  query_key,
  prefix_limit,
  ordered_ids,
  total,
  objects,
  email_progress,
  query_progress,
  completeness,
  pending_work
}
```

`ordered_ids` 必须是服务器查询结果的顺序。`objects` 只是当前前缀中已经取得的有限属性，不代表完整邮件对象。

### 5.4 完整性状态

```text
Ready
Pending
NeedsRefresh
Unsupported
ProtocolFailure
```

`Ready` 只表示：目标前缀已经填满或已确认服务器结果不足 N 条，所需邮件属性已经取得，已知变化和补位工作已处理完，两个状态链没有待追赶标记。

`Ready` 不表示服务器此刻不会继续变化，也不表示多个 JMAP 请求读到了一个全局原子快照。

## 六、核心算法

### 6.1 首次建立视图

1. 检查调用方传入的账号、能力和限制投影。
2. 取得 Email 类型状态基线，不把空 `Email/get` 误解为取得了邮件对象。
3. 生成固定的 `Email/query` 请求；当前核心 planner 在查询响应后生成使用显式 IDs 的独立 `Email/get` 请求。Python/MoonBit wire adapter 可以表达 RFC 的同批 `Email/get(#ids)` 形状，但核心不自动调度跨调用 batch。
4. 按邮件 ID 把 `Email/get` 返回的对象归位，不能假设返回顺序等于请求 ID 顺序。
5. 保存 queryState、Email 状态覆盖进度和有序 ID 前缀。
6. 处理建立视图期间产生的 Email 变化；如果变化影响查询成员或排序，重新协调查询。
7. 只有达到完整性条件才返回 `Ready`。

### 6.2 增量刷新

刷新时执行以下逻辑：

1. 用 EmailProgress 请求 `Email/changes`；
2. 用 QueryProgress 请求 `Email/queryChanges`；
3. 先从当前前缀删除 `removed`；
4. 再按 `added.index` 升序插入；
5. 对进入前缀、仍在前缀但属性已更新的邮件安排 `Email/get`；
6. 根据 total 裁剪或判断是否存在缺口；
7. 如果前缀不足 N，按同一 queryState 从缺口位置补取；
8. 如果补位返回了不同 queryState，拒绝拼接，重新查询前缀；
9. 如果 changes 期间报告了变化，继续追赶，不因为变化 ID 不在当前前缀就直接 Ready；
10. 两条状态链都没有待处理变化后才提交 checkpoint。

### 6.3 前缀补位

假设缓存为 `[a,b,c]`，目标长度为 3，b 被移出查询：

```text
[a,b,c] @ q0
应用 queryChanges -> [a,c] @ q1
query(position=2, limit=1) -> [d] @ q1
取得 d 的属性
提交 [a,c,d] @ q1
```

如果补位结果属于 q2，则不能直接提交 `[a,c,d]`，因为这三个元素不再有同一个查询状态依据，必须重新获取前缀。

### 6.4 失效恢复

| 情况 | 处理方式 |
|---|---|
| `queryChanges/cannotCalculateChanges` | 使查询状态失效，重新获取该查询前缀 |
| `changes/cannotCalculateChanges` | 使 Email 对象进度失效，重建所需对象状态 |
| `queryChanges/tooManyChanges` | v0.1 直接重新查询有界前缀 |
| 当前窗口对象 `notFound` | 标记本轮不完整，重新协调查询 |
| 响应缺失或格式错误 | 不推进 token，返回可恢复错误 |
| 超过字节、轮数或变更预算 | 返回 Pending/NeedsRefresh，并保存待办工作 |
| 账号或服务身份变化 | 拒绝复用旧 checkpoint |
| 旧请求响应晚到 | 根据请求代次丢弃，不能覆盖当前视图 |

## 七、与 Mooncakes 现有项目的隔离设计

| 已有能力 | MoonJMAP 的处理 |
|---|---|
| HTTP/Transport | 作为调用方注入的外部适配器，不在核心包实现 |
| FakeTransport/FakeServer | 只在测试目录保存最小响应夹具，不发布通用 mock 产品 |
| SSE/EventSource | 完全排除，应用如收到推送则显式调用 refresh |
| JSON/Pointer/Patch | 复用现有 JSON 库，只编码本项目固定请求结构 |
| IMAP/POP3/SMTP | 不做协议桥接，不解析 wire 命令 |
| MIME/附件/正文 | 不读取、不生成、不索引 |
| JSON-RPC | 不实现通用 dispatcher，只保留 JMAP 方法调用容器 |
| Workflow/Replay/Journal | checkpoint 只服务本项目恢复，不抽象为通用工作流产品 |
| 数据库事务 | 由调用方将 EmailViewUpdate 与 checkpoint 一起保存 |

公共模块只保留：

```text
moon_jmap/sync      视图、状态、增量计划和恢复
moon_jmap/jmap      四种方法的有限请求/响应类型
moon_jmap/email     固定视图配置和展示属性
tests/vectors/      RFC 对照向量和边界变化样例
examples/           通过外部 HTTP 库接入的薄示例
```

## 八、已落地的公共 API

下面列出当前 `src/sync/pkg.generated.mbti` 暴露的实现接口；它取代早期规划阶段的语义草案。字段名和构造方式以生成接口文件及 `src/sync/sync.mbt` 为准，调用方仍需自行把请求投影到 JMAP wire JSON。

```text
open_view(account, view_spec, limits, email_baseline) -> EmailView
open_view_with_capabilities(
  account, view_spec, capabilities, limits, email_baseline
) -> OpenViewResult

plan(view) -> Plan
refresh(view) -> RefreshStart
begin_refresh(view) -> RefreshStart
resume_with_email_state(view, fresh_email_state) -> RefreshStart
begin_resume_with_email_state(view, fresh_email_state) -> RefreshStart

accept_response(view, request_ticket, response) -> Acceptance
checkpoint(view) -> Checkpoint
restore_checkpoint(checkpoint, limits) -> Result[EmailView, String]
resumable(view) -> ResumableProgress
```

`Plan` 当前每次只含一个请求，描述下一次需要的四种 JMAP 方法之一，不负责实际发送；计划使用显式 ID，不能把 `ResultReference` 跨请求带入下一代。`RequestTicket` 包含账号、查询、请求代次、请求类型、期望 state、请求 ID、position 和 limit，用于拒绝旧响应和错配响应。`refresh`/`resume` 返回带有新 generation 的 `RefreshStart { view, plan }`，调用方必须使用返回的 `view` 接纳后续响应。`accept_response` 返回 `Continue`、`Commit`、`Pending`、`NeedsRefresh`、`Unsupported`、`ProtocolFailure` 或 `Dropped`，`Commit` 才携带可提交 checkpoint。

## 九、必须证明的验收场景

### 9.1 直接体现差异性的场景

1. 列表 `[a,b,c]` 不变，但 a 的 `keywords` 变化：必须更新 a 的属性。
2. b 从 `[a,b,c]` 中移出：必须补取 d，得到 `[a,c,d]`。
3. 同一个 ID 先 remove 后 add：按移动后的 index 处理，不能重复或丢失。
4. `removed` 包含本地未缓存 ID：不能把它当成错误。
5. 补位返回不同 queryState：不能混接两个状态的结果。
6. Email changes 历史失效而 queryState 仍有效：只使对象进度失效，重新取得需要的对象。
7. queryChanges 历史失效而 Email state 仍有效：重新查询有序前缀，独立保留可复用的对象。
8. 查询完成后，窗口外邮件进入筛选：必须再次追赶查询，不能错误输出 Ready。
9. get 观测到更新后的 state：不能跳过中间的 Email/changes。
10. 旧请求晚到：不能覆盖已经切换查询后的新视图。

### 9.2 资源和服务器限制场景

1. `maxCallsInRequest=1` 时分成两次请求，不能跨请求使用 ResultReference。
2. `maxObjectsInGet` 小于目标前缀时，返回明确的 Pending 或分段计划。
3. 服务器不支持指定 filter 或 sort 时，返回 Unsupported，不改成本地搜索。
4. 持续变化超出轮数或字节预算时，保留待办进度，不假报 Ready。
5. 空列表、少于 N、恰好 N 和服务器返回数量受限时，都不制造假缺口。

### 9.3 三层验证

- RFC 对照向量：人工独立确认请求、响应解释和最终视图；
- 小规模变化组合：增删、移动、属性变化和交错事件，与独立重取结果对照；
- 真实服务器互操作：至少记录一种独立 JMAP 服务的版本、配置、支持矩阵和原始响应。

模型测试只能证明模型内部一致性，不能替代真实服务器互操作。本项目已补充 Stalwart v0.16.27 的真实只读服务记录；公开文档仍必须把服务版本、部署方式和未覆盖范围写清楚，不能把单一实现结果扩展成普遍兼容。

## 十、开发阶段

实际执行状态：**M0–M3 已完成并通过本地验收，M4 的真实服务子项也已完成一条 Stalwart v0.16.27 只读路径**；托管 JMAP 服务和第二种服务实现仍未取得授权记录。下列“产物/退出条件”保留为逐项审查依据，具体证据见 `docs/validation-report.md`、`docs/differential-harness.md`、`tests/acceptance_matrix.md`、本地验收报告和真实服务验证报告。

### M0：差异化契约冻结，3–5 天（已完成）

产物：

- v0.1 支持矩阵；
- 状态归属和 token 绑定规则；
- Ready/Pending/NeedsRefresh 定义；
- 补位和失效手工向量；
- Mooncakes 相似项目排除清单。

退出条件：不再出现 HTTP、SSE、SMTP、IMAP、通用 RPC 或通用 JSON 工具扩张项。

### M1：视图建立，约 1 周（已完成）

产物：

- 固定查询配置；
- query→get 请求计划；
- 有序 ID 和对象属性归位；
- 基本 checkpoint；
- 空列表和不足 N 场景。

退出条件：能从一组固定响应生成一个完整前缀，但暂不宣称增量同步完成。

### M2：增量闭环，1–2 周（已完成）

产物：

- Email/changes 处理；
- Email/queryChanges 处理；
- 前缀删除、插入、裁剪和补位；
- 两条状态链协调；
- 三个核心演示全部可运行。

退出条件：增量结果与独立重新查询结果一致。

### M3：失效、预算和过期响应，约 1 周（已完成）

产物：

- 两类历史失效的不同恢复计划；
- 请求代次；
- 预算终止；
- Pending/NeedsRefresh checkpoint；
- 完整验收矩阵。

退出条件：失败时不会把旧数据、空列表或半完成列表标成 Ready。

### M4：独立互操作和发布说明，约 1 周（Stalwart 真实实现子项已完成）

已完成的本地和真实实现子项：

- 15 个合成场景的 MoonBit/Python 有界逐步对拍及已知边界清单；
- 3331 个当前 Mooncakes 模块的公开全量快照复核及 27 个增量包的校验记录；
- 依赖、许可证、稳定清单、路径安全和解包 smoke 检查；
- 本地源代码 tar/zip 归档与逐文件 SHA-256 manifest。
- 官方 Stalwart Server v0.16.27 本机真实实例上的 Session、四种只读 Mail
  方法和带 5 封合成邮件的对象级 HTTP 运行；20/20 请求返回 2xx，性能记录见
  `outputs/real-benchmark/stalwart-local-real-20261026-seeded.json`。
- 31 个公开可发现赛事候选的固定 HEAD、源码树和多信号审计；完整赛事名单仍由
  组委会掌握，公开候选审计见 `outputs/contest-public-inventory-2026-10-26.md`。

仍待外部条件的扩展子项：

- 第二种或托管 JMAP 服务授权；
- JMAP 写入以及非空创建/更新/删除/移动变化链；
- 组委会发布的完整赛事 roster、最终提交 commit/归档和官方判重标准。

退出条件：文档只宣传实际通过的能力，未验证的能力保留未完成标记。当前已完成
Stalwart v0.16.27 的真实只读记录和本机基准；托管服务、写操作、非空变化链、
OAuth/TLS、跨服务泛化和官方赛事全量判重仍不能从这些证据推出。

## 十一、已追加并落地的领域专属能力：邮件查询决策证书

在完成基础同步闭环后，增加了一项直接服务于 JMAP 邮件查询视图的能力：对一次
`Email/queryChanges`、`Email/changes`、`Email/get` 接纳前后的视图转移生成
`JmapEmailPrefixCertificate`（兼容 API 名 `DecisionCertificate`）。它不是通用日志、通用 patch、通用工作流或集合对账协议，证书只
回答一个问题：**这次有序邮件前缀为什么变成了当前结果，调用方能否脱机复核这个决定**。

实现已经落在 `src/sync/certificate.mbt`，并由 `certificate_test.mbt` 覆盖：

1. 证书绑定 `AccountScope`、`QueryKey`、generation、前后 query/email state、前缀上限、
   total、完整性和领域原因；账号与查询身份不一致或 generation 倒退时拒绝生成。
2. 对 before/after 有序 ID 计算 remove witness 和按最终位置排序的 add witness；纯重排
   无法用集合差表达时，确定性地退化为完整 remove 后按最终前缀重新 add，避免把移动误报为无变化。
3. `verify_certificate` 在纯 MoonBit 中重放 witness，检查 ID 唯一性、位置合法性、前缀
   长度、状态边界、证书分类和 after 前缀；`Ready` 没有有效双 state 时拒绝通过。
4. `certificate_from_acceptance` 覆盖 Continue、Commit、Pending、NeedsRefresh、
   Unsupported、ProtocolFailure 和 Dropped；晚到响应被丢弃时也能留下“没有改变视图”的可解释证据。
5. 证书使用固定摘要而不是运行时随机 hash，不包含正文、附件、Cookie、OAuth 或完整地址；
   它可以随 checkpoint 或 v2 trace 保存，但不替代 checkpoint，也不宣称远端服务器诚实。
6. `PrefixCoverage` 把连续前缀明确表示为 `[0,end)`，记录 `target_end`、`missing` 和
   `Open/Closed` frontier；同一 `queryState` 的缺口补位和 after 前缀的固定属性完整性
   分别记录为 `same_query_state_fill` 与 `objects_complete`，`Ready` 不能只靠 ID 数量通过。
7. `certificate_from_views_with_plan` 可附加 `EmailPrefixPlanBinding`，把单个
   `Email/query`、`Email/queryChanges`、`Email/get` 或 `Email/changes` 请求的
   generation、request id、position、limit、maxChanges、双 state、显式 ID、filter/sort
   摘要绑定进证书；验证器还按四种方法检查分页位置、limit、显式 ID 与前缀的关系，
   会拒绝复制其他查询、分页位置或代次的证书。

这项能力的差异化边界已经以 2026-10-26 的 3331 模块 Mooncakes 快照复核：未观察到以
JMAP 邮件查询前缀转移证书为目的的同类模块；仍然保留“指定快照内未观察到同目的实现”的
证据表述，不把它扩大为绝对原创或完全不重合结论。

## 十二、原创性和相似性证据方案

### 11.1 发布前重新核查

Mooncakes 目录会继续变化。发布或参赛前必须重新：

1. 获取当日完整模块清单；
2. 检查新增和版本变化；
3. 优先复核邮件、同步、协议、状态和查询类包；
4. 对候选包读取实际发布源码，而不是只看名称或 README；
5. 保存日期、目录 hash、包版本和复核结果。

### 11.2 对外可主张的内容

可以写：

> 在指定日期的 Mooncakes 公开目录和可读取发布源码中，未发现以 JMAP 邮件查询视图增量一致性与恢复为主要交付目标的同类模块。本项目仍复用了 JMAP 标准、JSON 基础和外部网络适配能力，不能据此声称绝对原创或不存在任何相似机制。

不能写：

- 全球首创；
- Mooncakes 完全没有类似项目；
- 原创 JMAP 协议；
- 自研 Transport/SSE/JSON-RPC 因而独有；
- 一定不会被判重；
- 已完成真实服务器兼容（除非有可复现记录）。

## 十三、停止扩张规则

以下需求一律不加入 v0.1：

- “顺便加一个 HTTP 客户端”；
- “顺便支持 IMAP/SMTP”；
- “顺便做完整邮件模型”；
- “顺便加入 SSE 自动刷新”；
- “顺便做通用状态机”；
- “顺便做一个 Web UI”；
- “顺便支持全部 JMAP 方法”。

如果未来需要这些能力，应单独评估是否复用 Mooncakes 现有项目，并且不能把它们写进 MoonJMAP 的原创主线。

## 十四、最终项目简介

### 一句话

> MoonJMAP 是一个面向 MoonBit 的 JMAP 邮件查询视图增量一致性内核，负责把 Email 对象变化、查询顺序变化、前缀补位和历史失效恢复协调成可提交的有序邮件视图，并为每次转移生成可脱机验证的邮件查询决策证书。

### 150 字简介

> MoonJMAP 不做通用邮件客户端，也不提供 HTTP、SMTP、IMAP、MIME 或 SSE。它只维护一个 JMAP 邮件查询的有界有序前缀，协调 `Email/changes` 与 `Email/queryChanges` 两条独立状态链，处理邮件属性更新、列表成员移动、删除后的同状态前缀补位、查询状态失效和可恢复 checkpoint，并用 `JmapEmailPrefixCertificate`（兼容 API 名 `DecisionCertificate`） 记录和验证一次前缀转移。项目的差异化来自 JMAP 邮件视图同步的专用状态模型、完整性判断、恢复计划和领域证书；JMAP 标准及网络、JSON 等基础能力按标准和外部依赖使用。

### 最终判断

这个规划的目标不是制造一个“完全没人碰过的基础概念”，而是把项目缩小到 Mooncakes 当前快照中未观察到同目的实现的一个明确工程问题。只有当代码真正完成“缓存 + JMAP 响应 → 正确新视图/下一请求/可恢复状态”时，这个差异化才成立。当前最新目录复核见 [MoonJMAP-Mooncakes最新全量复核-2026-10-25.md](MoonJMAP-Mooncakes最新全量复核-2026-10-25.md)，结论仍受快照、源码可读性和扫描方法限制。

## 十五、面向比赛评审的主线收敛（2026-10-25 更新）

本节是对前文“低重合”要求的对外叙事收敛，不增加新的通用模块。评审、演示和项目简介都应按下面的优先级展开。

### 15.1 第一主功能：JMAP 邮件查询前缀一致性

从一个固定的 JMAP 邮件查询开始，MoonJMAP 同时维护两条不能混用的 frontier：

```text
Email state frontier      -> 邮件属性是否已经追到指定状态
queryState frontier       -> 有序查询结果是否已经追到指定状态
```

这两条 frontier 共同决定一个连续的 `position=0` 前缀能否提交。评审应优先观察四个具体行为：

1. 列表顺序没有变化但 `keywords`/主题等属性变化时，只刷新受影响对象，不把“列表没动”误报成“对象没变”；
2. 中间 ID 被删除或移动时，按同一个 `queryState` 从缺口位置补位，不用本地猜排序，不制造假完整列表；
3. `Email/get` 返回顺序任意时按 ID 归位，缺失、重复、未请求 ID 和不完整字段都不能进入 `Ready`；
4. 任一历史失效、状态边界不一致或旧 generation 响应出现时，返回受控重建/丢弃结果，不能把半完成视图提交出去。

这四点是 MoonJMAP 的公共交付，也是和集合对账、数据库 CDC、通用增量计算、任务恢复工具发生实质区别的地方：它们必须理解 JMAP 的两个不透明 state、查询顺序和前缀完整性，而不是只处理一个稳定 ID 集合或通用事件流。

### 15.2 第二主功能：邮件查询决策证书

`JmapEmailPrefixCertificate`（兼容 API 名 `DecisionCertificate`） 不是另一个通用日志系统，而是上述前缀转移的领域证明。它把 before/after 有序 ID、remove witness、最终位置 add witness、两个 state 边界、generation、total、prefix limit 和 `Ready/Pending/NeedsRefresh/...` 原因绑定在一起，并由纯 MoonBit verifier 重放。

展示时应使用以下证据链：

```text
JMAP 响应接纳
  -> 双 frontier 与前缀变化
  -> JmapEmailPrefixCertificate
  -> 脱机 verifier 重放 after 前缀
```

这项能力的主张必须保持精确：在指定日期的 Mooncakes 公共目录和可读取发布载荷中，未观察到以 JMAP 邮件查询前缀转移证书为主要交付目标的模块。它仍然使用通用的 ID、数组和摘要算法，不能扩大为绝对原创或完全不重合。

### 15.3 相似能力降级清单

下面的机制保留在代码中，但对外只作为安全边界或测试证据，不作为项目重点：

| 机制 | 相邻项目中可见的共同概念 | MoonJMAP 的正确叙述 |
| --- | --- | --- |
| checkpoint、恢复、预算 | 集合对账、CDC、任务缓存和 workflow 都可能使用 | 只用于保存未完成邮件前缀，阻止跳过 Email/query history |
| generation、stale response、typed envelope | 通用异步状态机和协议适配器也会使用 | 只用于拒绝错误账号、旧请求和错配 state，保护本项目的 `Ready` 门禁 |
| Python wire、oracle、trace、metrics | JSON/RPC、replay、日志和可观测性项目也有类似工具 | 只用于复现 JMAP 四方法的固定边界；合成 trace 不代表线上性能 |
| tar/zip、manifest、smoke | 几乎所有可发布项目都需要 | 只证明本地源码交付完整，不能当作功能创新 |
| HTTP、TLS、OAuth、SSE、SMTP、IMAP、MIME | Mooncakes 中已有传输和邮件协议项目 | 明确由调用方/其他包提供或排除，不扩张 MoonJMAP 产品面 |

### 15.4 代码和演示的取舍规则

- 新增代码必须能直接改变前缀一致性、补位、双 frontier 协调、完整性门禁或决策证书验证之一；否则不进入主包。
- 新增示例必须以“旧视图 + JMAP 响应 → 新有序前缀 + certificate/下一计划”为结尾；不要用通用 HTTP、JSON、任务调度或日志示例占据演示入口。
- 预算、checkpoint、trace 和差分工具继续保留，因为它们是安全和证据所需；文档、竞赛材料和发布说明把它们放在主功能之后，并明确其内部支撑身份。
- 任何相似性结论都必须绑定日期、目录快照、源码可读范围和扫描方法；“完全没有类似项目”“保证不判重”等表述禁止使用。
