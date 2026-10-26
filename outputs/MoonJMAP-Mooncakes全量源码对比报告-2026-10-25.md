# MoonJMAP 与 Mooncakes 全量项目的源码对比报告

核查日期：2026 年 10 月 25 日（北京时间）。当前公开目录快照：2026-10-25T16:35:34.952522+08:00；结束复核：2026-10-25T16:43:49.305904+08:00。

## 1. 结论

**本次未发现能替代 MoonJMAP 规划主要交付的 JMAP Core / JMAP Mail 协议库；存在多类相邻项目和明显的组件、架构重合。** 因而可以继续按 JMAP 专用协议层推进，但不宜宣称“Mooncakes 没有类似项目”，也不宜把 Sans-I/O、Transport trait、fake transport、SSE 或普通 batch 单独写成独创点。

对比目标来自用户提供的 MoonJMAP 规划书：Sans-I/O JMAP Core + typed JMAP Mail client + fake transport/server fixtures；规划中的 HTTP、EventSource、blob 和邮件同步扩展一并纳入相邻性检查。规划书中的“未发现”声明仅作为待验证材料，没有直接采信。MoonJMAP 本身只提供了规划，故本次结论针对规划功能与现有实现的重叠；未来代码的相似度仍取决于实际实现。

**已逐项核查当前公开目录全部 3,304 个模块的指定发布包。** 全部 ZIP 可读取且 SHA-256 与官方 Git index 一致；没有只按包名或 README 排除项目。对每个模块留下版本、归档地址、文件数量、信号和判定记录。代码存在的包扫描实现、公开接口、测试、配置及其他可读文本；高信号候选再读实现上下文。该方法不等于人工逐行审阅全部项目。

## 2. 全量范围与完成证据

| 项目 | 本次结果 |
|---|---:|
| 当前 `/api/v0/modules` 中唯一模块 | 3,304 |
| 发布 ZIP 成功读取 / 官方 SHA-256 一致 | 3,304 / 3,304 |
| 扫描文本文件（含文档） | 302,874 |
| 非 Markdown 文本文件 | 276,780 |
| `.mbt` 源文件（含测试、示例、生成及随附第三方代码） | 147,490 |
| 全部可读文本 / 非 Markdown 文本体积 | 3.868 GB / 3.712 GB |
| 有候选语义、数值误报或特殊载荷复核记录的模块 | 167 |
| 补查历史发布版本 / 官方 SHA-256 一致 | 116 / 116 |
| 官方 Git index 历史元数据 | 19,942 条 |
| 当前目录含 yanked / prerelease 条目 | 92 / 16 |

官方前端的“Show All Modules”直接请求完整 `/api/v0/modules`，无需搜索分页。目录计数与 `/api/v0/modules/statistics` 的 `total_modules=3304` 一致。开始和结束快照的名字、版本及原始 JSON SHA-256 完全相同，核查窗口内未发生目录漂移。

原始发布包中，3,255 个复用同日已经取得的对应版本归档，49 个重新下载。所有归档均在本轮重新计算哈希，并与独立更新的官方 Git index 的 checksum 比对；没有复用其他项目的相似性结论。官方索引提交为 `a3eaed97c6c8608daa5fe954218e2fe488ad9e33`，时间为北京时间 2026-10-25 16:32:29。

当前以模块名精确匹配并保留大小写；没有合并 `xunyoyo/permutation` / `xunyoyo/Permutation` 或 `youyong5/moontetris` / `youyong5/MoonTetris`。同一项目的旧名 `justinwongcn/openpgp` 和现名 `justinwongcn/moonpgp` 均保留逐模块记录，解释实际竞争项目时作为沿革处理。

## 3. 判定标准与实际检查

| 判定 | 所需实现证据 |
|---|---|
| 直接重复 | 可调用的 JMAP Core 与相当的 Mail 方法，或能实质替代规划主要交付的 JMAP 协议库 |
| 实质同类 | 真实实现 JMAP 核心语义/邮件子集，或形成足以替代主要模块的顺序 batch、先前结果引用、数据类型状态同步组合 |
| 领域相邻 | SMTP、IMAP、POP3、MIME、Maildir、Sieve、邮件对象或归档、认证/通知等 |
| 组件或局部机制相似 | HTTP、SSE、JSON-RPC、JSON Pointer/Patch、mock、其他协议的批写或乐观前置条件等 |

全包扫描不仅检索 JMAP/RFC 名字，还检查 `urn:ietf:params:jmap`、`methodCalls/methodResponses`、`resultOf`、`ifInState`、`stateMismatch`、`cannotCalculateChanges`、`invalidResultReference`、`sessionState`、`queryState`、`eventSourceUrl`、`primaryAccounts`、Mailbox/Email/Thread 方法、关键邮件字段，并覆盖大小写和下划线变体。邮件、JSON-RPC、Pointer、SSE、HTTP 等低特异信号用于扩大召回，不能单独用于认定重复。

非 Markdown 文件中，JMAP capability URN 和 `Mailbox/get`、`Email/query` 等方法签名均为 0 命中。JMAP 名称/核心字段/状态字段召回的 46 个模块（含已专项复核的 SSE）均已结合上下文解释；裸数字 8620/8621 召回的 53 个模块另外检查，严格 RFC 引用为 0。其余邮件初筛又用严格协议词和 wire 命令补扫，发现了包名不含 mail 的 `chensuiyi/bm2` 等下游集成。

典型误报包括 JavaScript `JMap`、JSON Schema 内部 map AST、`pdfobjmap` 子串、字体编码中的随机字节、Tree-sitter `QueryState`、PowerShell `SessionState`、解释器的 `method_calls` 计数和测试里的 `result_of`。这些均未直接当成 JMAP。

## 4. 最需要正面承认的相似项目

下表位置均对应本次核验的精确发布 ZIP 内文件；完整源码片段、测试/接口证据及每包判定在证据包与逐项对照表中。

| 已有模块 | 源码确认的交集 | 与 MoonJMAP 的边界 |
|---|---|---|
| `gaato/http@0.5.0` | `src/transport.mbt:12` 是真实 Transport trait；`src/mock/transport.mbt:30,115` 是 FakeTransport 及其 trait 实现；`src/sse/parser.mbt:29,94` 是增量 SSE parser | 传输注入、离线模拟和 SSE 基础层高度重合。缺少 JMAP 请求信封、结果引用、数据类型状态与 Mail 方法，可优先作为依赖 |
| `q2316367743/moonhttp@0.6.0` | `src/transport/transport.mbt:215`、`mock.mbt:11,77`、`src/client/sse_stream.mbt:21,97` 已实现 Transport、mock、HTTP、SSE | 通用 HTTP 客户端；这些架构能力不构成 JMAP 专用实现 |
| `huanglong44/imap@0.7.0` | Sans-I/O decoder、typed UID/FETCH、会话与 Maildir；`session.mbt:18,61,76` 使用单 pending 和 IMAP tag | 邮件协议和设计思路相邻。IMAP 认证/选择阶段及 UIDVALIDITY 不等于 JMAP 类型级 state |
| `cheng-jun56/pop3@0.5.0` | `protocol.mbt:7,26,104`、`session.mbt:5,39` 实现 POP3 命令与会话阶段 | Sans-I/O 协议引擎相邻，实际 wire 为 POP3，不含 JMAP batch/引用/Mail API |
| `howhere7/moonmail@0.1.0`、`nexacodes/email@0.1.0` | 类型化邮件、MIME、SMTP 与 fake/stub transports；前者 `client.mbt:65`，后者 `transport/smtp_native.mbt:827,839,859` | 邮件发送及工程组件相似，远端协议为 SMTP |
| `fhh12341/mailkit_12314@0.1.0` | 邮件模型、附件、线程与查询；`search.mbt:112` 遍历本地 MailMessage 数组 | 本地解析/检索，不是 RFC 8621 的远端 Email/query/get/set 与 account/state 语义 |
| `liubin-dev/mailbox@0.10.0` | `mbox_stream.mbt:5,16`、`maildir.mbt:9` 实现 mboxrd、Maildir 和 MIME 集成 | 可以承接归档环节；不是 JMAP 同步协议 |
| `gmlewis/jsonrpc2@0.0.34`、`shiguri-01/jsonrpc@0.3.0` | 前者 `message.mbt:12,151` 有 batch 数组；后者 `src/endpoint.mbt:204,216,267` 逐项 dispatch 并传递原始 params | JSON-RPC 2.0 对象批处理不提供 JMAP 的先前响应路径引用及 ifInState |
| `f4ah6o/sse@0.3.1` | JS EventSource、重连、native SSE server；`src/sse/reconnection.mbt:3,69` | EventSource/重连已有实现；JMAP StateChange 解释和 session URL 绑定仍需协议层完成 |
| `moonrockz/smithy-validation@0.6.0` | JSON-RPC batch 校验、会话状态、Pointer 提取能力声明；`rpc/transcript_order.mbt:160,294` | batch 允许任意顺序，Pointer 更新 advertised 能力集合，没有先前结果参数替换或 JMAP 数据类型状态 |
| `marianoguerra/atproto@0.1.3` | typed XRPC、transport、blob、applyWrites 批写和 swapCommit CID 前置条件 | 具有批量操作和乐观前置条件的局部交集；实际为 AT Protocol 的 `/xrpc/<nsid>`，无 JMAP Core/Mail 组合 |
| `vectie/moonproj@0.1.0-preview.3` | 批量业务创建、幂等回放、revision、expected_state guard；还含 email outbox 模型 | 状态属于企业业务流程；没有动态先前响应引用。邮件命令明确 dryRun、providerExecution=false |
| `moonbitstack/moonjson`、`Freesia666/moonjsonpath`、`JingLan0v0/moonpatch`、`Xu107-hhh/moonbit-jsonpatch` | JSON、Pointer、RFC 6902 Patch、Merge Patch 等基础操作已有真实实现 | 可复用路径与JSON基础；RFC 6902 操作数组和 Merge Patch 均不能直接冒充 JMAP PatchObject/ResultReference |
| `justinwongcn/moonpgp@0.1.0`（旧名 openpgp） | 不仅有 OpenPGP，还含实际 SMTP/IMAP 示例；`example/netmail/imap.mbt:650`、`smtp.mbt:166` | 已有邮件收发场景，协议仍是 IMAP+SMTP，没有 JMAP |
| MIME、邮件鉴权、Sieve、通知及网关各包 | MoonMIME、mbt-email、mbt-mailauth、mailshield、moonsieve、notify、imrelay、bm2 等均有真实代码 | 内容解析、安全策略、规则或通知相邻；不覆盖规划中的 JMAP Core/Mail 主交付 |

## 5. 全部模块的逐项分类

| 类别 | 模块数 |
|---|---:|
| 静态筛查未召回直接同类 | 3,137 |
| 命中经语义/数值复核排除 | 110 |
| 邮件/内容/身份领域相邻 | 19 |
| 基础组件或架构局部重合 | 19 |
| 特殊载荷：无当前实现或数据/示例 | 15 |
| 其他协议或工作流的局部机制相似 | 4 |

各类别合计 3,304 个精确模块，逐项对照表每个模块恰好一行。“静态筛查未召回”表示在公开发布载荷和已列模式下未找到直接同类，不能扩写成形式化证明该项目所有可能代码均不相关。

## 6. 空壳、历史名称与嵌套归档

13 个当前发布包没有实现源码，另有 1 个 JPEG/标注数据包和 1 个仅带 AST helper/测试的 skill 包。逐个检查了实际载荷，未用 README 替代源码判断。13 个空壳/迁移/移除包分别补查一个前一官方源码版本，均完成官方 checksum 校验；其实现属于数学、基础工具、dotenv、Tree-sitter、迭代器、运算符或 Unix CLI，未见 JMAP。详细坐标及证据保存在逐项表和证据包，历史源码没有被冒充为当前发布源码。

除全部当前版本外，补扫历史包合计 116 个：RPC/传输 101 个、IMAP/mailbox 2 个、空壳前一源码版本 13 个；116 个归档均成功读取且 SHA-256 与官方索引一致。全部 19,942 条历史元数据还单独搜索过 JMAP/RFC8620/RFC8621，没有专用命中。**没有对全部 19,942 个历史版本逐包做源码扫描。**

官方 Git index 比当前网站清单多出 13 个历史嵌套名字，包括 `moonbitlang/lex/runtime`、`tonyfettes/js/test`、`tonyfettes/tree-sitter/cli` 等。其独立 ZIP 均返回 404；3 个 manifest 路径实际返回父模块，另 10 个返回 404。已保留补充表，但没有把父模块响应充作这些旧坐标的独立源码证据。

进一步检查了发布 ZIP 内的 83 个嵌套归档，递归遇到 134 个对象，成功读取 1,150 个附加文本，JMAP 高特异信号为 0。另有 63 条解析错误，涉及 29 个外层模块，多为 `target/publish` 自包含截断/损坏构建 ZIP；全部错误路径与原因均保留，没有将其记作完整可读源码。它们不影响外层官方 ZIP 及已发布可读源文件的 checksum/静态核查事实。

## 7. 对规划定位的建议

项目适合保留的差异化主线是 **RFC 8620/8621 的具体协议语义组合**：Session/capability/using、三元组方法信封、先前结果的 `#argument + resultOf/name/path`（含数组映射展开）、数据类型级 state/ifInState、Mail 类型和错误、blob/session URL 模板及 StateChange 适配。HTTP、Pointer、SSE、mock 和邮件内容处理宜说明复用边界。

建议把原规划的“空白证据”改为：

> 截至 2026 年 10 月 25 日本次核查窗口，已逐项检查 Mooncakes 当前公开目录 3,304 个模块的发布载荷，结合源码特征扫描、候选实现/接口/测试复核与 116 个相关历史版本补查，未发现可替代本项目主要交付的 JMAP Core/Mail 专用实现。生态中已有 SMTP/IMAP/POP3/MIME/Maildir、JSON-RPC、HTTP/SSE、JSON Pointer/Patch 及测试组件；本项目的预期差异在 JMAP 专用方法、结果引用和状态语义。该结论受公开快照、源码可得性和静态方法限制，不代表绝对原创或赛事认定。

源码对比时也发现规划有几处 RFC 范围需澄清：

1. **`Thread/query` 不是 RFC 8621 标准方法。** §3 定义 Thread/get、Thread/changes；线程列表通常通过 Email/query 的 collapseThreads 产生。
2. `state` 表示账号内某个数据类型集合的状态，不能解释为每个对象单独的版本；queryState、sessionState 也需区分。
3. position/limit 分页属于 /query；/get 是按 IDs 获取并受对象数量限制。
4. ResultReference 只能引用先前调用结果，需实现 `#参数`、resultOf/name/path、`*` 映射展开及参数冲突检查；只做通用 JSON Pointer 不够。
5. 一次方法调用可能产生多条携带同一 call ID 的响应，数据结构不能固定一调用一响应。
6. 如果首版只做子集，应发布 RFC 支持矩阵，明确 Core/echo、creation IDs、PatchObject、changes/queryChanges 等范围，避免把计划子集写成完整 Core。

本次未修改原规划书，未执行下载包的代码或测试；引用测试内容仅证明包中包含这些用例，不代表其运行通过或互操作合格。本次“未发现”也不构成赛事接受、法律原创性或未来代码不存在相似性的保证。

## 8. 复核入口与交付文件

- 全量目录：[Mooncakes modules](https://mooncakes.io/api/v0/modules)
- 计数：[官方 statistics](https://mooncakes.io/api/v0/modules/statistics)
- 官方版本/哈希索引：[Git index](https://mooncakes.io/git/index)
- 指定模块 manifest：`https://mooncakes.io/api/v0/manifest/{owner}/{module}`
- 精确版本发布源码：`https://download.mooncakes.io/user/{owner}/{module}/{version}.zip`
- [RFC 8620 §3.7 ResultReference](https://www.rfc-editor.org/rfc/rfc8620.html#section-3.7)
- [RFC 8620 §5 标准方法与状态](https://www.rfc-editor.org/rfc/rfc8620.html#section-5)
- [RFC 8621 §3 Thread](https://www.rfc-editor.org/rfc/rfc8621.html#section-3)

交付包括可检索 HTML、全部 3,304 行 CSV、本报告、统计 JSON、13 条历史索引补充 JSON，以及源码核查证据 ZIP。证据 ZIP 含官方快照、每个文本文件的包内路径/字节数/哈希/信号、候选源码片段与行号、历史核查、嵌套归档错误和复扫脚本；不把其他任务的报告或既有判定当作本次证据。
