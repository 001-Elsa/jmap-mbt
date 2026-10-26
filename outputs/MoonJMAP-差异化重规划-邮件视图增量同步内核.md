# MoonJMAP 差异化重规划：JMAP 邮件查询前缀一致性与决策证书

规划日期：2026 年 10 月 25 日。本文是新的产品与工程方案；核心接口和场景已经落地，实际验证证据见 `docs/validation-report.md` 和 2026-10-26 真实服务验证报告。Stalwart v0.16.27 的真实实现互操作已取得脱敏记录；发布和赛事认定仍需独立证据，不由本地模型测试替代。

## 1. 建议直接采用的定位

**把 MoonJMAP 从“JMAP Core / Mail 全面协议栈”改成“JMAP 邮件视图增量同步内核”。首版只解决一个问题：应用已缓存某个 JMAP 邮件查询的前 N 条结果后，怎样在新增、属性更新、移出、排序变化及增量历史失效时，正确更新这份列表。**

建议保留 MoonJMAP 名称，副标题改为：

> 面向 MoonBit 的 JMAP 邮件视图增量同步内核。

对开发者的一句话说明：

> 输入账号、邮件视图定义、已有缓存和 JMAP 响应，输出下一批 JMAP 请求与可提交的视图更新。

“视图”有明确边界：服务器端某个 `Email/query` 的有序 ID 前缀，加上这些 ID 对应的有限邮件属性。它服务于收件箱列表、未读列表和只读邮件仪表板，不承担完整邮箱镜像或邮件备份。

这个方向能够避开现有邻居的大部分主交付用途。仍然会使用 JSON、容器、状态转换、批请求等共同机制；这些机制和 JMAP 标准本身不能写成作者独创。可以用范围和证据降低重复风险，不能保证赛事“绝不判重”。

## 2. 为什么选择这条主线

原规划同时包含 HTTP、Transport、FakeTransport、SSE、blob、邮件类型、协议会话和跨协议同步，产品中心分散，容易被理解为已有组件的集合。

新规划围绕 JMAP 中两个不同的同步事实展开：

| 要维护的事实 | 使用的方法与状态 | 单独实现时会漏掉什么 |
| --- | --- | --- |
| 哪些邮件属于这个列表、各自排第几 | `Email/query`、`Email/queryChanges`、`queryState` | 列表成员和顺序不变时，邮件的 keywords 等属性仍可能变化 |
| 已缓存邮件的属性是否需要更新、邮件是否被销毁 | `Email/get`、`Email/changes`、账号内 Email 数据类型的 `state` | 无法据此自行还原服务器定义的查询成员与排序 |

项目的核心工作是把这两条状态链协调成可用列表，补齐窗口缺口，并在证据不足时选择重新获取。应用不应自己散落地拼接四种方法、维护两个不相容的 token、猜测何时可以保存同步进度。

**标准出处也必须正面说明：RFC 8621 §4.10 已给出组合 Email/changes 与 Email/queryChanges 更新邮件缓存的示例，包括删除、插入、刷新已有邮件属性以及用回引用获取邮件。** 因此，两条状态链协同的基本流程属于标准已有内容；这里寻求的是 MoonBit 生态的实用实现缺口，以及边界、恢复和使用契约的工程完成度。

**验收对象必须是“更新后的邮件视图 + 正确的下一步请求/同步状态”。仅有 DTO、编解码、批请求构造、错误枚举或一份校验报告，不算主目标完成。**

## 3. 对用户列出的相似项目逐项处理

以下依据已有源码审计，不是重新按 README 推断功能。版本保持本次审计坐标。

| 相邻项目 | 从自研主交付中删除的范围 | 新规划的边界与保留工作 |
| --- | --- | --- |
| `gaato/http@0.5.0` | 自建 Transport trait、FIFO FakeTransport、HTTP、增量 SSE parser | 核心只生成 JMAP JSON 请求、消费响应；示例接入现有 HTTP 库，不发布另一套传输框架 |
| `q2316367743/moonhttp@0.6.0` | HTTP client、可注入 transport、mock、流式下载和 SSE | 不扩展网络客户端；从已有 HTTP 库中选择一套接入即可 |
| `huanglong44/imap@0.7.0`、`cheng-jun56/pop3@0.5.0` | IMAP/POP3 命令、wire parser、会话阶段、UID 与 Maildir | 不做 IMAP↔JMAP 桥接；同步依据 JMAP Email 类型状态及 queryState，不处理其他邮件协议 |
| `howhere7/moonmail@0.1.0`、`nexacodes/email@0.1.0` | SMTP、MIME builder、通用邮件收发客户端、可替换邮件传输 | 只接收 JMAP 服务器已经结构化的列表属性，不实现发送和内容编码 |
| `fhh12341/mailkit_12314@0.1.0`、`liubin-dev/mailbox@0.10.0` | 本地邮件搜索、线程推导、附件处理、mboxrd、Maildir | 查询和排序由 JMAP 服务器完成；本地只维护服务器返回的视图，不建设邮件索引库 |
| `gmlewis/jsonrpc2@0.0.34`、`shiguri-01/jsonrpc@0.3.0` | 通用 RPC dispatcher、JSON-RPC 兼容层、通用 batch scheduler | 只构造所需的 JMAP 三元组与顺序请求；不将普通 batch 宣传为独有能力 |
| `f4ah6o/sse@0.3.1` | EventSource、重连、SSE server | 刷新由调用方显式触发；如果应用已收到推送，可以调用 refresh，库不接管推送连接 |
| MoonJSON、MoonJSONPath、MoonPatch、moonbit-jsonpatch 等 | 自研通用 JSON、Pointer、JSON Patch、Merge Patch 库 | 用现有 JSON 基础；wire adapter 只保留固定 `/ids` ResultReference 形状，sync planner 使用显式 ID，不发布路径执行器，也不实现 PatchObject |
| `moonrockz/smithy-validation@0.6.0` | 任意协议 transcript validator、schema/session 规则 DSL、通用 Pointer 能力提取 | 不以“协议审计报告”为主产品；固定 JMAP 语义直接驱动邮件缓存与后续方法调用 |
| `marianoguerra/atproto@0.1.3` | 广覆盖 typed client、blob、批写、乐观写前置条件 | 首版只读，删除 `Email/set` 和 `ifInState`；聚焦 Email 对象增量与有序查询增量的协调 |
| MoonPGP、MoonMIME、MoonSieve、邮件鉴权和通知网关 | 加解密、MIME、规则语言、反垃圾、鉴权策略、通知与邮件投递 | 不提供邮件内容、安全或通知平台；它们可作为上层应用的独立能力 |

还要额外守住几条边界，避免改规划后落入另一批邻居：

| 其他已核查的邻居 | 新规划不扩展的产品方向 |
| --- | --- |
| `LAOBIAO656/moonreplaykit@0.2.0` | 不导出通用 journal/reducer、回放迁移比较器；检查点只服务本项目同步恢复 |
| `Lyl66655/moonbit-workflow-engine@0.1.4` | 不导出任意 task/action、DAG、状态机 DSL、通用重试编排器 |
| `zkc-long/faultcanvas@0.1.0` | 不发布 HTTP 故障代理、fake server、服务虚拟化平台；响应夹具只放测试目录 |
| `vectie/moonproj@0.1.0-preview.3` | 不做业务批创建、通用幂等日志、revision guard，不承诺 exactly-once 写入 |

这里的“避开”是删除重复产品范围并如实复用基础设施。为了字面上的“零相似”去重新发明 JSON 或更换常规数据结构，不会提升项目的实质差异。

## 4. 应做深的四项具体能力

### 4.1 账号 Email 状态与查询状态分别推进

维护两个有身份约束的进度：

- Email 数据进度：账号内 Email 集合的变化处理到了哪里。
- 查询进度：同一账号、同一查询定义的有序结果变化处理到了哪里。

邮件仍在列表中、位置也未变，不代表属性没有变化。反过来，知道某封邮件被更新，不代表知道它在查询里的新位置。

### 4.2 有界前缀的增量维护和补位

按 RFC 规定先应用 `removed`，再按 `added.index` 升序插入。删除、移出或重新插入可能使前 N 条出现未知尾部；内核须补取，且检查补取结果是否仍属于同一 queryState。不能简单做 ID 集合差集，也不能把不足 N 条当作完整窗口。

### 4.3 按失效对象恢复，而不是统一清空或统一重试

- 查询历史失效：重建查询 ID 前缀，仍有独立有效性依据的对象可复用。
- Email 变化历史失效：使该账号 Email 对象缓存失效，重新取得所需对象；查询 ID 的有效性单独判断。
- 网络失败、响应缺失、获取时出现 `notFound`：保留明确的未完成状态，不能冒充空列表或已同步。

### 4.4 只提交有依据的本地进度

每次提交同时携带视图内容、对应查询状态、已处理的 Email 进度及完整性标记。不能只保存最新看到的 token，而把尚未处理的变化跳过去。

以上是对标准的专用工程实现。可主张的贡献在于把这些规则整合成可调用、可恢复、可验证的内核；ResultReference、queryChanges 和 state 的定义仍来自 RFC。

## 5. v0.1 的硬范围

**一个实例维护一个账号中的一个只读 Email 视图，缓存从位置 0 开始的连续前 N 条。**

| 内容 | v0.1 决定 |
| --- | --- |
| 标准方法 | `Email/query`、`Email/queryChanges`、`Email/get`、`Email/changes` |
| 视图配置 | 先支持“某 Mailbox 最新邮件”和“某 Mailbox 未读邮件”，均按 `receivedAt` 降序；不做通用搜索表达式 builder |
| Mailbox 选择 | 调用方提供 mailboxId；不新增 Mailbox 管理模块 |
| 展示属性 | 限定为 `id`、`threadId`、`mailboxIds`、`keywords`、`receivedAt`、`subject`、`from`、`preview`；不取正文、附件或 bodyStructure |
| 线程 | `collapseThreads=false`；不实现 Thread/get，更不存在 RFC 标准的 Thread/query |
| 结果引用 | wire adapter 可编码 query→get 所需的固定 `#ids`、`resultOf`、`name`、`path:"/ids"`；当前 sync planner 每个计划只生成一个调用并使用显式 ID，不实现通用引用解析器、`*` 路径执行器或依赖图调度器 |
| 账号与能力 | 接收应用提供的 Session 必需字段投影，检查账号具备 Mail 能力及相关请求限制；不实现网络发现或 OAuth |
| 列表长度 | 默认 N=50，配置值受应用预算与服务器能力约束；`maxObjectsInGet` 限制每批 `Email/get` 对象数，N 可以更大但必须分段，并受轮数、字节和对象预算约束 |
| 请求与同步预算 | 限制响应字节、对象数量、每页 changes 数量、处理轮数与总变更量；超出预算返回未完成状态 |
| 总数 | v0.1 的 query/queryChanges 请求 `calculateTotal=true`，用来判断前缀应有多长；成本纳入性能记录 |
| 状态保存 | 导出版本化的邮件视图 checkpoint；存储介质、数据库事务由调用方负责 |
| 网络 | 示例连接一个已有 HTTP 库；核心无自建 HTTP/Transport/FakeTransport |

未读查询采用标准 Email filter 的 `inMailbox` 与 `notKeyword:"$seen"`。服务器不支持所选过滤/排序时返回明确不支持信息，不偷偷切换为本地搜索。

不做：写入、`ifInState`、creation IDs、PatchObject、EmailSubmission、blob、SSE、SMTP/IMAP/POP3/MIME、跨协议迁移、完整 JMAP server、通用审计器或通用 mock server。

**发布名称和支持矩阵必须写“JMAP 邮件视图同步子集”，不能写“完整 RFC 8620 Core / RFC 8621 Mail 实现”。**

## 6. 状态与检查点契约

以下契约已经落到 `src/sync/sync.mbt` 的公开状态模型，并由 MoonBit 测试、独立 Python oracle 和向量回放共同验收。代码仍保持规划中的边界：这是一个固定查询视图的同步内核，不是完整 JMAP 客户端；真实服务器互操作已按 `docs/interop-record-template.md` 记录 Stalwart v0.16.27 的四种只读方法，证据见 2026-10-26 真实服务验证报告。

```text
AccountScope = 应用指定的服务身份 + accountId

QueryKey = AccountScope + Email + filter + sort + collapseThreads

EmailProgress = AccountScope + 已覆盖的 Email state
QueryProgress = QueryKey + queryState

ViewCheckpoint = {
  format_version,
  account_scope,
  query_key,
  property_projection,
  prefix_limit,
  ordered_ids,
  total,
  email_objects,
  email_progress,
  query_progress,
  completeness,
  pending_work
}
```

约束：

1. 所有状态字符串不透明，只做相等判断或原样回传；不比较数值、字典序或“新旧大小”。
2. `state` 是账号内 Email 数据类型集合的状态，不是每封邮件的对象版本；queryState 与 sessionState 也分别处理。
3. filter、sort 或 collapseThreads 改变，旧 queryState 不得复用。投影改变则重新核对对象属性覆盖；改变 N 要重新核对前缀覆盖。
4. 查询 token 的归属来自账号和查询上下文；不能把同一个 token 字符串视为可在其他上下文使用的全局版本号。
5. `EmailProgress` 表示库已处理到的变更覆盖进度。个别对象可能由更晚的 get 读到，因此不声称所有对象恰好是该 state 时刻的快照。
6. v0.1 每个实例只允许一个在途同步计划；响应票据绑定实例代次，避免切换查询后的慢响应覆盖新视图。
7. 旧缓存可以由应用保留作带过期标记的展示；失效的缓存不得继续用作同步完成的依据。

`Ready` 的含义限定为：当前已观测响应支持一个完整的目标前缀；所需对象均取得、无已知脏项、无待处理的 changes 页面或查询补位。它不代表服务器此刻仍未变化，也不代表多种方法读取了同一时刻的全局原子快照。

`pending_work` 至少保存 Email 需追赶、查询需追赶、未完成变化页、待取对象与前缀缺口；两条状态链的待追赶标记都清除后才可能 Ready。

## 7. 已实现的同步流程（截至 2026-10-25）

### 7.1 首次建立视图

1. 从调用方提供的 Session 投影检查账号、Core/Mail 能力与服务器限制。
2. 先用 `Email/get(ids:[])` 取得 Email 类型状态基线 `s0`，不借此声称已获取任何对象。
3. 由当前 sync planner 生成一个 `Email/query(position:0, limit:N)` 计划；查询响应接纳后，再生成使用实际显式 IDs 的独立 `Email/get` 计划。这样不会把跨请求的 `ResultReference` 当成仍然有效。Python/MoonBit wire adapter 可以按 RFC 形状编码固定的同批 `Email/get(#ids)`，但 v0.1 核心不自动调度多调用 batch，也不扩展为通用请求拆分框架。
4. 保存 queryState 和有序 ID；get 返回对象按 ID 归位，不能相信 `list` 与请求 IDs 的顺序相同。
5. 从 `s0` 继续 `/changes` 协调查询和对象获取期间的变化。后续 get 看到的 state 只是观测信息，不直接覆盖已处理进度。
6. 缺对象、出现 `notFound`、服务器限制使前缀未填满，或仍有已知变化时继续计划；初始化查询之后的变化追赶若又报告变化，必须再次协调查询，规则同 7.2；预算内满足契约才输出 Ready。

下面是 wire adapter 可编码的 RFC 请求形状示例；它用于验证固定 ResultReference 的线协议容器，不表示当前 sync planner 会自动生成同批请求：

```json
{
  "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
  "methodCalls": [
    ["Email/query", {
      "accountId": "a1",
      "filter": {"inMailbox": "inbox1"},
      "sort": [{"property": "receivedAt", "isAscending": false}],
      "collapseThreads": false,
      "position": 0,
      "limit": 3,
      "calculateTotal": true
    }, "q1"],
    ["Email/get", {
      "accountId": "a1",
      "#ids": {"resultOf": "q1", "name": "Email/query", "path": "/ids"},
      "properties": ["id", "threadId", "mailboxIds", "keywords", "receivedAt", "subject", "from", "preview"]
    }, "g1"]
  ]
}
```

如果调用方选择使用该 wire 形状，由服务器执行 ResultReference 参数替换；客户端负责编码合法引用、处理引用失败并消费响应。当前核心默认使用显式 ID 的单调用计划，因此不会在内部跨请求复用该引用。

### 7.2 已有缓存后的增量刷新

1. 用已覆盖的 Email state 发 `Email/changes`，用 queryState 发 `Email/queryChanges`；当前核心按一调用一个计划依次生成两种请求，并把 changes 放在 queryChanges 之前。外部适配器可以自行批量，但不能改变请求票据和响应接纳顺序。
2. 分别校验 `accountId`、`oldState` / `oldQueryState`、请求票据与查询上下文。
3. query delta 先移除当前前缀中的 removed IDs，再按 added.index 升序处理插入。`removed` 含未缓存 ID 是合法情况；同一 ID 的 remove→add 可以表示移动。
4. 只在插入位置不超过当前已知连续前缀长度时直接插入，最多保留 N 条。未知尾部不填成假 ID，不凭本地排序推断位置。
5. 根据 total 计算目标长度 `min(N,total)`，超出部分裁剪。如果已知前缀不足，按 7.3 补位。
6. 取当前前缀中新进入、缺失，以及被 changes 标记为 updated 的邮件属性；不因全账号大量变化而抓取所有非视图邮件。
7. changes 的 created/updated/destroyed 可有 RFC 允许的交集，需去重并按删除及后续响应语义处理，不能假定三个互斥集合。
8. 处理本页所需对象后，记录该页 newState 覆盖进度。若 hasMoreChanges=true，从该 newState 继续；中间 token 不代表时间顺序。
9. 若 get 观测到不同的类型状态，从已覆盖进度继续 changes，不能跳到这个新 token 以省掉尚未处理的变化。
10. **查询之后又处理的 changes 页面只要报告了变化，或又观察到尚未覆盖的类型 state，即把查询标记为需追赶，即使所有变更 ID 都不在当前前缀。** 未缓存邮件也可能刚刚进入筛选或改变列表顺序。重新调用 queryChanges 或重取前缀后，才清除该标记。观察到尚未覆盖的 get state 时也不能直接 Ready，须完成 changes 追赶及查询复核。
11. 实现采用保守时序 `changes → queryChanges/重取 query → 所需对象 get → 再次 changes`；末次 changes 仍有变化则继续协调。对象已取得、变化页处理完、前缀覆盖完整且两链均无待追赶标记后才输出 Ready。这个循环策略是本项目的实现选择，不宣称 RFC 指定了完全相同的算法。
12. 达到预算返回 Pending/NeedsRefresh，并保留待追赶标记和可恢复信息。

### 7.3 前缀补位

假设 query delta 已把前缀推进到 `q1`，已知连续前缀长度为 L，目标是 K：

1. 请求同一查询的 `Email/query(position:L, limit:K-L)`。
2. 只有返回的 queryState 等于 `q1`、position/total 等字段满足本轮契约时，才把结果接到前缀尾部。
3. 若 queryState 不同，不拼接不同状态的两段；重新从 position 0 查询前缀，再协调对象变化。
4. 服务器实际限制使返回不足时，继续补位或在预算达到后返回未完成。

常见的 `inMailbox` 和 keywords 筛选都涉及可变属性。**v0.1 不发 `upToId`，不假设服务器只返回前 N 条相关增量。** 面对全账号大变化，预算和降级策略比虚构这种优化更可靠。

### 7.4 失效与失败的确定行为

| 收到的情况 | 下一步 | 不允许的捷径 |
| --- | --- | --- |
| `Email/queryChanges: cannotCalculateChanges` | 使此查询 ID 缓存失效，重新 query 前缀；对象缓存按其独立有效性决定复用 | 把错误当成空 delta，继续推进旧列表 |
| `Email/changes: cannotCalculateChanges` | 使该账号 Email 对象缓存失效，重新取得所需对象并建立基线；查询状态单独协调 | 保留旧属性却换上最新 state |
| `Email/queryChanges: tooManyChanges` | v0.1 直接重新 query 有界前缀 | 把 queryChanges 当成有 hasMoreChanges 的分页协议 |
| `canCalculateChanges=false` | 用 query 重取成员顺序；仍可独立使用 Email/changes 刷新对象 | 声称此服务器上查询 delta 已得到验证 |
| get.notFound 命中当前窗口 ID | 标记该轮不完整，重新协调查询；必要时重取前缀 | 本地删掉 ID 后凭空调整顺序/total 并宣称 Ready |
| 缺响应、malformed body、超限或未知失败 | 不推进未经验证的进度，返回错误或可继续计划 | 用空对象、空列表替代失败 |
| 账号/服务身份改变，账号权限不再可用 | 拒绝复用原 checkpoint，要求应用更新上下文 | 把不同账号的同名 token 接成同一条链 |
| 持续变化导致超出轮数/字节/变更预算 | 返回 Pending/NeedsRefresh 及已有进度，等待下一次显式 refresh | 无限自动循环，或声称已经取得全局一致快照 |

JMAP batch 中的方法有执行顺序，但整个 batch 不是事务。同一 callId 在协议上可能对应多条响应；底层容器必须保留响应列表，不能以 callId→单响应覆盖信息。首版只生成自己的只读方法，不因此宣传完整隐式方法支持。

## 8. 三个主演示，均以邮件视图结果验收

### 演示 A：列表没动，属性仍然刷新

旧视图 `[a,b,c]`；a 的 keywords 改变，列表成员/顺序不变。queryState 可以保持相同，但 Email state 改变。

预期：应用后的列表仍为 `[a,b,c]`，a 的属性已更新；库没有因为“列表没变”跳过 Email/changes，也没有重新抓取未受影响的全部对象。

### 演示 B：未知尾部补位，避免少一行

旧服务器完整结果 `[a,b,c,d]`，本地 N=3，只缓存 `[a,b,c]`。b 移出查询后，queryChanges 只给 `removed:[b]`、`added:[]`、`total:3`。

预期步骤：

```text
已有前缀 [a,b,c] @ q0
应用 delta -> [a,c] @ q1，尚不完整
请求 query(position=2, limit=1)
收到 [d] @ q1 -> 前缀 [a,c,d]
取得 d 的属性，并处理尚未覆盖的 Email 变化
输出可提交的新视图
```

若补位返回 q2，必须重新校准前缀，不能拼成“前两项属于 q1、最后一项属于 q2”的 Ready 视图。

### 演示 C：增量历史过期后继续提供可用视图

分别让查询历史和 Email 变化历史失效。

预期：两类失效有不同重建计划；旧缓存可被标记为过期展示，新视图满足契约后再替换；失败过程不能产生“空邮箱”假象，也不能丢失未完成标记。

这三个演示优先于 HTTP 压测、SSE 重连、邮件发送或通用报告页面。它们直接解释为何需要这个 JMAP 专用包。

## 9. 已实现的公开 API 与模块边界

以下是当前 MoonBit 实际公开 API 的语义摘要；精确签名以 `src/sync/pkg.generated.mbti`、
`src/jmap/pkg.generated.mbti` 和 `src/email/pkg.generated.mbti` 为准。Python wire adapter
位于 `src/jmap`，只覆盖同一固定四方法子集。

```text
open_view(account_scope, view_spec, limits, email_baseline)
  -> EmailView

open_view_with_capabilities(account_scope, view_spec, capabilities, limits,
                            email_baseline)
  -> Accepted(EmailView) | Unsupported(reason) | InvalidInput(reason)

plan(view)
  -> Plan

refresh(view) / begin_refresh(view)
  -> RefreshStart { view: EmailView, plan: Plan }

resume_with_email_state(view, state) /
begin_resume_with_email_state(view, state)
  -> RefreshStart { view: EmailView, plan: Plan }

accept_response(view, request_ticket, response)
  -> Continue(ContinueResult)
   | Commit(CommitResult)
   | Pending(PendingResult)
   | NeedsRefresh(reason, ResumableProgress)
   | Unsupported(reason)
   | ProtocolFailure(reason)
   | Dropped(reason)

checkpoint(view) / restore_checkpoint(saved, limits)
  -> Checkpoint / Result[EmailView, reason]
```

`RefreshStart.view` 是已递增请求代次的新视图，调用方必须把它和返回的
`RefreshStart.plan` 一起作为后续 `accept_response` 的输入；旧的 `view` 不能再接收
这批响应。`resume_with_email_state` 仅在调用方提供新的 Email state 后重建对象进度，
仍保留可复用的 query progress；它同样返回新代次，避免旧请求覆盖恢复中的视图。

`CommitResult` 输出本次可提交的有序 IDs、对象替换/失效及完整性信息。首版直接输出有界的新前缀，避免再造通用 diff 算法。调用方把更新和 checkpoint 一起保存；核心不能替调用方保证数据库事务。

`Commit` 只用于满足 Ready 契约的视图。Continue/NeedsRefresh 中可以导出带未完成标记的恢复进度，但调用方不能把它当成已同步的视图提交。

当前只有以下产品模块：

```text
moon_jmap/sync      公共邮件视图与同步入口
moon_jmap/jmap      四种方法所需的信封、响应及有限 Session 投影
moon_jmap/email     有限列表属性与具体 view spec
examples/          通过已有 HTTP 库接入的薄示例
tests/vectors/     RFC 对照向量和同步边界样例
```

内部可以有状态、请求和前缀处理文件，但不导出 transport、fake_server、workflow、replay、generic_validator 等子产品。依赖选择核对目标后端、接口、许可后确定；本规划不把“可以复用”写成“已集成成功”。

## 10. 正确性验收矩阵与当前结果

以下是实现后的验收要求和当前结果。M0–M3 的本地状态模型、请求边界、失效恢复和
完整性约束已执行；真实服务器互操作属于 M4，已取得 Stalwart v0.16.27 的脱敏原始响应和性能报告。

| 验收组 | 必须出现的行为 |
| --- | --- |
| 身份与 token | 相同字符串位于不同账号、不同查询或不同状态种类时不可混用；不比较 token 大小 |
| 初次建立 | 空列表、少于 N、恰好 N、大于 N、服务器缩小 query limit；get 返回顺序与 IDs 不同 |
| 属性变化 | queryState 不变、Email state 变化时刷新被影响的缓存对象 |
| 查询 delta | 新成员插入、移出、同 ID remove+add、removed 含未缓存 ID、加入位置在前缀外 |
| 前缀覆盖 | 删除中间/尾部后原有后方邮件补位；补位期间 queryState 改变时拒绝混接 |
| changes 链 | 多页 hasMoreChanges、中间 token 非单调、ID 集合合法交集、只刷新当前缓存所需对象 |
| get 与游标 | get 看到更新 state 时不跳过 changes；notFound 触发协调；失败不推进已覆盖进度 |
| 两链再协调 | 查询完成后的 changes 报告窗口外邮件进入筛选时，必须再次追赶查询；不能因当前对象均已获取而错误 Ready |
| 引用与响应 | wire adapter 的 query→#ids get 形状；前调用失败引发 invalidResultReference 时不当成空列表；响应容器不覆盖同 callId 多响应；sync planner 默认使用显式 IDs 单调用计划 |
| 失效恢复 | queryChanges 与 changes 的 cannotCalculateChanges 分别失效；queryChanges tooManyChanges 改为重取前缀 |
| 请求与资源边界 | `maxCallsInRequest=1` 时分请求且不跨请求引用；能力/方法限制、服务端不支持过滤/排序、超字节/轮数/变更预算、持续变化时明确未完成 |
| 恢复与过期响应 | checkpoint 重开可继续；查询切换后的旧请求响应不能覆盖新视图 |

验证分三层：

1. **RFC 对照向量**：逐项写预期请求、响应解释及最终视图；关键预期由独立审查确认，避免同一段实现自己生成答案再验证自己。
2. **小规模变化组合**：对有界 ID 列表生成增删/移动/属性更新及交错事件；在服务状态可比较的条件下，把增量结果与独立重取的目标前缀作对照。模型结果只证明模型内行为。
3. **真实服务器互操作**：至少记录一种独立 JMAP 实现的版本、配置、四种方法支持与实际响应；当前已完成 Stalwart v0.16.27，条件允许再补第二种。不得把本次本机 loopback 结果扩展成所有服务兼容或官方认证。

还应记录请求次数、对象获取数、响应字节及重建次数，分别比较稳定列表、小变化和增量失效场景。合成向量指标已由 `docs/metrics-benchmark.md` 记录，真实服务测量已由 `outputs/MoonJMAP-真实服务互操作与性能验证-2026-10-26.md` 和 `outputs/real-benchmark/stalwart-local-real-20261026-seeded.json` 记录；这些结果只代表对应数据规模、服务版本和 loopback 环境，不作公网吞吐或生产 SLO 承诺。前 N 条并不保证 `/changes` 只返回 N 条，也不保证每轮都比重查更省流量。

## 11. 开发里程碑与停止扩张的条件

原规划按一名熟悉 MoonBit 的开发者估算约 4–6 周；本次已完成 M0–M3 的本地实现与验收，并完成 M4 的有界跨实现对拍、Mooncakes 公开全量目录复核、本地源代码交付门禁和 Stalwart v0.16.27 真实服务互操作/性能测量。

| 阶段 | 预计投入 | 可审查产物与退出条件 |
| --- | --- | --- |
| M0 契约定稿 | 3–5 天 | **已完成**：四种方法支持矩阵、状态归属、前缀完整性与失败策略；手工向量确认补位/分页规则 |
| M1 建立视图 | 约 1 周 | **已完成**：能力投影、query→get 请求、属性归位、有限前缀和空/短结果 |
| M2 增量闭环 | 1–2 周 | **已完成**：两条状态链、delta、补位、changes 分页、对象抓取与安全进度；三个主演示可运行 |
| M3 失效与恢复 | 约 1 周 | **已完成**：不同失效范围、checkpoint 恢复、过期响应、预算终止；本地验收矩阵通过 |
| M4 独立互操作与说明 | 约 1 周 | **Stalwart 真实实现子项已完成**：有界跨实现对拍 15/15、当前 3331 模块目录复核、可复现源代码归档与 smoke、四种只读方法真实响应和 5 轮真实性能测量已完成；第二种托管服务和跨后端测试矩阵仍待授权 |

若 M2/M3 未完成，不加 blob、写入、SSE 或 UI 门户凑完整度。M4 的 Stalwart v0.16.27 真实只读路径和本机基准已经取得；后续若要扩展到第二种服务或托管环境，仍须分别取得授权、记录版本和保存脱敏证据，不能把当前结果外推为普遍兼容。

## 12. 后续只沿同步问题纵向深化

在本轮实现中，已先落地一项低重合的同步专属扩展：`JmapEmailPrefixCertificate`（兼容 API 名 `DecisionCertificate`）。它把一次
有序邮件前缀的 before/after 变化、remove/add witness、双 state 边界、generation、完整性
和原因绑定成可脱机验证的证书；移动邮件会退化为确定性的全量 remove+final-position add，
`verify_certificate` 会重放证书并拒绝重复 ID、非法位置、状态倒退和 Ready 缺少双 state。
该功能只服务 JMAP 邮件查询视图的解释与审计，不是通用 patch、通用日志、通用 workflow 或
集合对账。证书现在还包含 `PrefixCoverage`（Open/Closed、target_end、missing、同 queryState 补位和对象完整性）以及可选的 `EmailPrefixPlanBinding`（方法、generation、request id、分页位置、limit、maxChanges、双 state、filter/sort 与请求 ID 摘要）；验证器会拒绝复制其他查询、页码或代次的证书。实现、测试和边界见 `src/sync/certificate.mbt`、`src/sync/certificate_test.mbt`
与 `docs/decision-certificates.md`。

| 后续方向 | 仍然解决的同一问题 | 进入条件 |
| --- | --- | --- |
| 多视图共享一个账号对象缓存 | 收件箱/未读/星标列表共享 Email 变更处理，减少重复获取并准确传播失效 | 单视图闭环稳定；定义共享覆盖进度和各视图查询进度的边界 |
| `collapseThreads=true` 视图 | 同一线程代表邮件随查询变化替换，仍需维护正确顺序和属性 | 有折叠视图专属验收；使用标准 Email/query，不虚构 Thread/query |
| 大列表稀疏窗口与更精细补位 | 只缓存部分区间时仍正确应用全局 added.index、缺口与 total | 连续前缀策略有实测瓶颈；先设计未知区间表示与覆盖证明 |

后续仍不纳入邮件发送、MIME、通用客户端、跨协议迁移或事件编排平台。若未来有真实需求，应另行评估与生态项目的重叠。

## 13. 差异证据、宣传与判重准备

### 13.1 目前能够成立的事实

本次最新源码审计覆盖 2026-10-26 的 Mooncakes 公开目录当前 3,331 个模块版本快照；旧 3,304 个已审计记录加上本轮 27 个新增或版本变化包组成当前覆盖，全部下载包与 manifest checksum 一致。目录快照 SHA-256 为 `3e086048fc1dbffd5b9fa5a01eaf5c56b8e1c983cb7e1856440f10600f2cd57e`，证据见 `work/live-scan-2026-10-26/` 和 `outputs/mooncakes-public-comparison-2026-10-26/report.md`。该审计未观察到能替代 JMAP 专用主交付的实现，同时确认了集合对账、CDC、workflow、HTTP/SSE 和邮件协议等真实相似性。

这次复核覆盖当前目录的全量 `(name, version)`，但仍只代表指定日期、公开载荷和既定静态读取方法；没有把历史私有代码、不可下载版本或未来发布声称为已读。新的同步定位在 JMAP 范围内进一步收敛，现有证据支持“该快照中未观察到同目的的 JMAP 视图同步模块”，不足以证明所有项目不存在任何相似机制。

### 13.2 已取得与仍需取得的证据

- **已取得**：主 API 完成“旧缓存 + JMAP 响应 → 正确新视图/下一请求/可恢复 checkpoint”。
- **已取得**：专属测试区分双状态、前缀缺口、查询移动、changes 分页、能力限制、预算、完整性和分层失效；MoonBit wasm/wasm-gc 各 47/47，bundled Node JS 47/47，Python wire 13/13（合并 Python 回归 16/16），独立 oracle 17/17，向量回放 15/15；有界跨实现逐步对拍 15/15。
- **已取得**：复用边界和依赖来源已在支持矩阵、README 与源码对照材料中说明；工程交付集中在标准规则的 MoonBit 实现、前缀与状态表示、检查点提交约束、资源预算及恢复协调。
- **仍需取得**：至少一种独立服务器的可复现互操作记录，包含版本、能力投影、四种方法响应和未覆盖项；当前不得把本地证据写成服务兼容。
- 发布/参赛前仍应按最终代码与最终范围更新相邻包版本，复核新增模块；对赛事“同题/同功能/代码相似”的具体规则另行核对。

这些工作提高可辩护性，仍不能替评审作结论。换名、压低依赖数量、增加页面或堆测试数量都不能单独证明原创性。

### 13.3 当前实现阶段可使用的介绍

> MoonJMAP 是面向 MoonBit 的 JMAP 邮件视图增量同步内核，协调账号内 Email 数据变化与特定查询的有序结果变化，覆盖前缀补位、增量分页和历史失效恢复。HTTP、SSE、SMTP/IMAP、MIME、邮件发送及通用协议框架不属于其主交付。依据 2026 年 10 月 26 日的 Mooncakes 公开发布源码审计，尚未观察到同目的的 JMAP 专用实现；这一结论有快照和方法边界，不构成绝对原创性或赛事判定保证。真实 Stalwart v0.16.27 只读互操作已验证，不能扩展为所有服务兼容。

本地实现和验收已完成；M4 已有可复现的 Stalwart v0.16.27 真实服务器记录。对外只列实际通过的四种只读方法、测试账号范围和本机性能口径，不把该结果扩展为通用 JMAP 兼容或生产性能保证。

不要使用：“全球首创”“Mooncakes 完全没有类似”“原创 JMAP 协议”“自研 Sans-I/O/batch/状态机因此独有”“完整 RFC 实现”“绝不会判重”。

## 14. 依据与回查入口

- [最新 Mooncakes 全量复核报告](MoonJMAP-Mooncakes最新全量复核-2026-10-25.md)
- [已完成的 Mooncakes 全量源码对比报告](MoonJMAP-Mooncakes全量源码对比报告-2026-10-25.md)
- 3,304 模块可检索逐项对照表 (`outputs/MoonJMAP-Mooncakes逐项对照-3304模块.html`; local-only evidence)
- 源码核查证据包 (`outputs/MoonJMAP-源码核查证据-2026-10-25.zip`; local-only evidence)
- [RFC 8620 §3.3 请求与方法执行顺序](https://www.rfc-editor.org/rfc/rfc8620.html#section-3.3)
- [RFC 8620 §3.4 响应对象](https://www.rfc-editor.org/rfc/rfc8620.html#section-3.4)
- [RFC 8620 §3.7 ResultReference](https://www.rfc-editor.org/rfc/rfc8620.html#section-3.7)
- [RFC 8620 §5.1 /get 与类型状态](https://www.rfc-editor.org/rfc/rfc8620.html#section-5.1)
- [RFC 8620 §5.2 /changes](https://www.rfc-editor.org/rfc/rfc8620.html#section-5.2)
- [RFC 8620 §5.5 /query](https://www.rfc-editor.org/rfc/rfc8620.html#section-5.5)
- [RFC 8620 §5.6 /queryChanges](https://www.rfc-editor.org/rfc/rfc8620.html#section-5.6)
- [RFC 8621 §4.2–4.5 Email 读取、变化与查询](https://www.rfc-editor.org/rfc/rfc8621.html#section-4.2)
- [RFC 8621 §4.4.3 线程折叠](https://www.rfc-editor.org/rfc/rfc8621.html#section-4.4.3)
- [RFC 8621 §4.10 邮件视图与增量同步示例](https://www.rfc-editor.org/rfc/rfc8621.html#section-4.10)
