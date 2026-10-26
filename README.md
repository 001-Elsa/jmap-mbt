# MoonJMAP

Mooncakes：[`001-Elsa/moonjmap@0.1.0`](https://mooncakes.io/docs/001-Elsa/moonjmap)。注册表构建与独立安装验证已通过，见 [发布记录](docs/mooncakes-release-0.1.0.md)。

源码仓库：[001-Elsa/jmap-mbt](https://github.com/001-Elsa/jmap-mbt)。本次将既有源码快照按功能和文件时间线整理为 20 次实质提交；提交时间为实际整理时间。发布范围、历史证据和脱敏说明见 [仓库导入说明](docs/repository-import.md)。

MoonJMAP 的主交付是：**把 JMAP 邮件查询的两条变化链，收敛成满足本地同步契约的有序前缀**。它接收调用方已经取得的 JMAP 响应，输出新的有序邮件前缀、下一批明确的 JMAP 请求，或者带有待办工作的恢复状态。核心包不建立网络连接，也不实现 SMTP、IMAP、MIME、SSE 或通用 JSON/RPC。

项目的第二个主功能是面向这个邮件视图的 **JmapEmailPrefixCertificate**（兼容 API 名 `DecisionCertificate`）：证书以 `FromBefore(index)` / `Introduced(id)` 逐位置解释新前缀，记录 `PrefixCoverage`、同 `queryState` 补位、对象完整性、两个 JMAP state 边界、generation，以及保存完整 typed Request 的可选 `EmailPrefixPlanBinding`。查询身份直接比较结构化 `QueryKey`，纯 MoonBit 验证器不依赖指纹或通用编辑脚本。它回答的是“这次列表为什么变成这样、是否可以安全提交”，而不是提供通用 patch、日志或工作流。

## 给评审的功能主线

建议按下面的顺序理解和评审 MoonJMAP：

1. **JMAP 邮件前缀一致性（核心）**：分别追踪 `Email/changes` 的对象属性历史和 `Email/queryChanges` 的查询顺序历史；处理成员移动、属性变化、删除后的同状态补位、历史失效和旧响应；只有前缀、对象属性和两条 state 链都满足契约时才报告 `Ready`。
2. **邮件查询决策证书（核心扩展）**：从一次接纳结果生成领域专用证书，按最终前缀位置记录旧位置引用或新进入 ID，离线验证 after 前缀、state 边界、generation 和结果分类。证书不携带实际邮件字段，不能独立复核对象载荷来源。
3. **恢复和资源边界（内部支撑）**：checkpoint、generation fence、`max_changes`、Pending/NeedsRefresh、typed response bridge 只用于保证上面两项的安全性，不单独构成产品卖点。
4. **测试和交付工具（证据，不是产品功能）**：Python wire 容器、独立 oracle、MoonBit/Python 对拍、synthetic trace、指标脚本和源代码归档用于证明核心行为；它们不应被介绍成通用 RPC、通用 replay、通用日志、通用性能平台或通用发布系统。

### 相似能力如何处理

Mooncakes 目录中可以找到与本项目共享机制的邻近实现：`moonreconcile` 处理稳定 ID 集合差异和恢复，`MoonCDC` 处理数据库变更流和投影，`incr` 处理增量重算，`moon_taskforge` 和 `moonreplaykit` 处理任务/事件恢复，`gaato/http` 及邮件协议包处理传输和邮件协议。深化复核还确认 `moontxnwitness` 存在实际字段来源、前缀交付门禁与独立 trace 重算，`medseal` 存在领域对象重读与引用闭合，`moon_historycheck` 存在独立义务重算。这些项目说明前后载荷核查、审计闭合，以及预算、checkpoint、状态机、集合差异、HTTP、JSON 等通用机制都不是 MoonJMAP 独有。

因此 MoonJMAP 对这些能力采取以下边界：

| 能力 | 项目中的地位 | 评审时应看什么 |
| --- | --- | --- |
| HTTP、TLS、OAuth、Session、SSE | 外部适配器或明确排除 | 不把传输栈重复实现算作创新 |
| JSON、RPC、ResultReference 容器 | 固定 JMAP wire 支撑 | 只检查四个方法的契约投影，不宣传通用 JSON/RPC |
| checkpoint、预算、generation、Pending | 一致性安全机制 | 看它们是否阻止错误 `Ready`、旧响应覆盖和预算跳过 |
| trace、metrics、差分 harness、Python oracle | 测试证据 | 看是否覆盖核心前缀/双 state/证书场景，不把合成指标当线上性能 |
| 邮件协议、MIME、正文、附件、发送 | 明确排除 | 不扩展为邮件客户端或协议工具包 |
| 有序前缀补位、双 state 协调、ID 归位、JmapEmailPrefixCertificate | **主功能** | 看能否从固定 JMAP 响应得到正确前缀、可解释证书和安全下一步 |

“指定快照内未观察到同目的实现”是本项目可以使用的证据措辞；它不等同于绝对原创，也不保证评审方不会基于共享基础机制作相似性判断。项目的低重合策略是减少通用功能面，把代码、演示和篇幅集中在 JMAP 邮件查询前缀一致性及其决策证书上。

2026-10-26 的完整归档文本复核覆盖当前目录 3,331 个精确 `(name, version)` 模块；09:52:20 重新取得的目录与该扫描快照一致。本轮还对候选“载荷/trace 闭合审计”方案重读全部归档文本，发现 MoonTxnWitness 等强架构邻居，因此该新增层已撤回，没有进入当前源码或公共 API。证据包、回放、字段变更记录、闭环门禁、CDC、集合对账和分页都有邻近项目；保留现有 JMAP 窄领域定位不等于已证明原创或无判重风险。依据见 [方案核对与撤回说明](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E6%B7%B1%E5%8C%96%E6%96%B9%E6%A1%88%E5%85%A8%E9%87%8F%E6%A0%B8%E5%AF%B9%E4%B8%8E%E6%92%A4%E5%9B%9E%E8%AF%B4%E6%98%8E-2026-10-26.md)，前次原有功能核查见 [源码复核](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E7%8B%AC%E6%9C%89%E5%8A%9F%E8%83%BD%E4%B8%8E%E7%9B%B8%E4%BC%BC%E6%8A%80%E6%9C%AF%E5%A4%8D%E6%A0%B8-2026-10-26.md)。

> 当前仓库按 v0.1 规划收敛。真实服务实现互操作和性能必须以脱敏外部证据为准，不能由本地单元测试替代；本次已补充 Stalwart v0.16.27 真实实现的本机部署记录，托管邮箱服务仍需单独授权。

## 当前差异化重构

2026-10-26 的本地实现进一步收窄了通用机制代码面：

- `Email/queryChanges` 以服务端给出的最终排名归并旧前缀存活项和新增项，直接生成可证明的连续前缀；未知排名仍要求刷新。
- 前缀证书改用位置引用，删除通用 remove/add 编辑脚本；查询和请求绑定改用结构化字段，删除 FNV 与摘要判定。
- 邮件对象变化只接受 RFC `created/updated/destroyed/has_more_changes` 模型，移除早期 `ChangesData` 两数组兼容入口。

checkpoint、预算、generation、Ready 门禁及独立验证仍有既有技术先例。此次改变不构成零相似或算法原创证明。证书字段与旧变化响应入口有本地 API 不兼容调整，详见 [证书结构与迁移](docs/decision-certificates.md)。改造前的全量审计报告保留为历史快照，不能把其中的 FNV、remove/add 证书描述套用于当前源码。

最终冻结源码的 wasm、wasm-gc、使用 Codex bundled Node 的 JS 测试各 **86/86** 通过，native 静态检查通过；其中包含 93,072 组最终排名归并对拍和 4,225 种位置证书转移。Python 回归 26/26、独立 oracle 17/17、固定向量和有界跨实现对拍各 15/15。详细变更、与指定近邻的实测差值和证据边界见 [本次差异化改造报告](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E5%B7%AE%E5%BC%82%E5%8C%96%E6%94%B9%E9%80%A0%E4%B8%8E%E5%A4%8D%E6%A0%B8-2026-10-26.md)。这些结果没有重新验证真实服务器互操作或生产性能。

## 代码边界

| 目录 | 责任 |
| --- | --- |
| `src/email` | **主功能输入模型**：两种固定查询视图和展示字段投影 |
| `src/jmap` | JMAP 四方法的有限 wire 投影；只为主功能提供边界，不是通用 RPC |
| `src/sync` | **主功能实现**：双 state 链、前缀补位、响应接纳、恢复与完整性判断 |
| `src/sync/certificate.mbt` | **主功能扩展**：邮件查询决策证书与纯 MoonBit 验证器 |
| `python/moonjmap` | 历史 Python 兼容模型；仅供迁移参考，不属于 v0.1 公共 API 或验收对象 |
| `tests/vectors` | 可读的 RFC 对照和边界变化夹具 |
| `examples` | 不连接网络的最小响应回放；属于证据，不是独立产品 |
| `docs` | 支持矩阵、状态契约、验收记录和互操作模板 |

核心代码已包含在 `src/email`、`src/jmap` 和 `src/sync`；`tests/vectors` 和 `examples` 仍可独立用于确认协议场景的预期行为。它们属于本地模型证据，不会伪装成真实服务器验证。

## 安装与使用

Mooncakes 包名为 `001-Elsa/moonjmap`，版本为 `0.1.0`。在已有 MoonBit 工程中添加：

```sh
moon add 001-Elsa/moonjmap@0.1.0
```

在使用邮件视图的包的 `moon.pkg` 中导入：

```moonbit
import {
  "001-Elsa/moonjmap/src/email" @email,
  "001-Elsa/moonjmap/src/sync" @sync,
}
```

下面的测试会构造一个本地视图，并取得第一批查询计划；网络请求由调用方执行：

```moonbit
test "open a bounded mail view" {
  let account : @sync.AccountScope = {
    service_identity: "https://jmap.example.test",
    account_id: "account-1",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("email-state-0"),
  )
  let next = @sync.plan(view)
  assert_eq(next.requests.length(), 1)
  assert_true(next.requests[0].kind == @sync.RequestKind::Query)
}
```

第三个公共包 `001-Elsa/moonjmap/src/jmap` 提供有限的 MoonBit wire 类型。根包保持为空；Python 探针与审计脚本随源码提供，不属于 MoonBit 公共 API。Mooncakes 包通过 `.moonignore` 排除本地调查、历史输出和构建产物，历史证据从 GitHub 仓库查看。

## 快速查看

```sh
python3 examples/replay_vectors.py
python3 examples/codec_roundtrip.py
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
moon check --target native
moon check --target js
moon check --target wasm-gc
moon test --target wasm-gc
```

脚本只使用 Python 标准库，读取 `tests/vectors/incremental_cases.json`，检查每个向量的初始顺序、变化应用顺序、补位状态和最终完整性。它是协议语义的独立可读 oracle，不替代 MoonBit 核心实现的测试。

2026-10-26 撤回新增审计层后、此次差异化改造前的源码，MoonBit `wasm`、`wasm-gc`、使用 Codex bundled Node 的 JS 测试各 78/78 通过；其中包含原有证书修复的 4,225 种转移穷举和 27 条同步边界回归。Python wire/HTTP 探针回归为 26/26，独立状态机 oracle 为 17/17，向量回放为 15/15。MoonBit `native`、`js` 静态检查均 rc0。本轮没有扩展实服验证：此前 Stalwart v0.16.27 的本机只读记录解析了 25 个 Email 对象，5 轮、20 请求的脱敏证据见 [真实服务验证报告](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E7%9C%9F%E5%AE%9E%E6%9C%8D%E5%8A%A1%E4%BA%92%E6%93%8D%E4%BD%9C%E4%B8%8E%E6%80%A7%E8%83%BD%E9%AA%8C%E8%AF%81-2026-10-26.md) 和 [对象级互操作记录](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/real-interop-stalwart-v0.16.27/record-seeded-object-level-20261026.json)。性能结果只代表本机 loopback 和合成数据，不是公网 SLO；非空运行原始响应未保存，因此不把它写成已重新通过 typed decoder。

跨实现逐事件对拍可运行：`python3 scripts/run_differential.py` 会启动 MoonBit
`wasm` trace adapter，并把 C01–C15 的有序前缀、opaque state、generation 和
下一请求投影与独立 Python 回放逐步比较；当前结果为 15/15，机器证据见
[`outputs/MoonJMAP-跨实现逐步对拍-2026-10-25.json`](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E8%B7%A8%E5%AE%9E%E7%8E%B0%E9%80%90%E6%AD%A5%E5%AF%B9%E6%8B%8D-2026-10-25.json)，
解释和边界见 [`docs/differential-harness.md`](docs/differential-harness.md)。
这是一组有界共同投影比较，不是完整跨语言等价证明，也不替代真实服务记录。

## 设计承诺

* `AccountScope`、`QueryKey`、`EmailProgress` 和 `QueryProgress` 分开绑定；token 不跨账号、查询或状态类型复用。
* `Ready` 只在有界前缀和所需对象属性已齐备、两条状态链无待追赶工作时返回。
* 删除前缀成员后按同一个 `queryState` 补位；补位返回不同状态时转为重建。
* 历史失效只使对应状态链失效，不能把另一条链的进度一起推进。
* 请求代次、预算和响应结构检查在提交 checkpoint 之前生效；旧响应不能覆盖新查询。
  `checked_next_generation` 拒绝负值和 `@int.MAX_VALUE`，避免 refresh/resume 的
  generation 回绕；旧 API 在这个边界返回协议失败视图和空计划。
* `Email/changes` 分页按 `Limits.max_changes` 设定累计条目上限；每页请求携带剩余
  `maxChanges`，`changes_seen` 随 checkpoint 持久化，预算耗尽保持 Pending 而不跳过
  未消费的历史。

评审主线不是“支持了多少通用基础设施”，而是以下闭环是否成立：

```text
固定 JMAP query 视图
  + Email/changes（对象属性 frontier）
  + Email/queryChanges（有序查询 frontier）
  -> 最终排名归并与同-state 前缀补位
  -> 需要时受控重建
  -> Ready 的有序前缀 + JmapEmailPrefixCertificate
```

每个内部机制都必须能回指这个闭环：预算用于避免跳过历史，generation 用于拒绝晚到响应，checkpoint 用于恢复未完成前缀，trace 和对拍用于证明决策；脱离这个闭环的通用能力不进入公共定位。

详细定义见：

* [支持矩阵](docs/support-matrix.md)
* [状态和 checkpoint 契约](docs/state-contract.md)
* [恢复、预算和旧响应处理](docs/recovery-and-budget.md)
* [可追溯同步 trace 格式](docs/trace-schema.md)
* [邮件查询决策证书与纯 MoonBit 验证器](docs/decision-certificates.md)
* [合成视图指标与预算基准](docs/metrics-benchmark.md)
* [向量和演示验收报告](docs/validation-report.md)
* [真实服务互操作与性能验证报告](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E7%9C%9F%E5%AE%9E%E6%9C%8D%E5%8A%A1%E4%BA%92%E6%93%8D%E4%BD%9C%E4%B8%8E%E6%80%A7%E8%83%BD%E9%AA%8C%E8%AF%81-2026-10-26.md)
* [外部事项完成度与 31 个公开赛事候选审计](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E5%A4%96%E9%83%A8%E4%BA%8B%E9%A1%B9%E5%AE%8C%E6%88%90%E5%BA%A6-2026-10-26.md)
* [真实服务互操作记录模板](docs/interop-record-template.md)
* [本地发布检查清单](docs/release-checklist.md)

## 本地源代码包

项目提供可重复构建的本地源代码归档。它只打包明确列出的源码、夹具、
文档和许可证。`outputs/` 下经筛选的公开证据随 Git 仓库提供，源代码压缩包不包含这些历史输出；阅读压缩包中的证据链接时请访问上面的源码仓库。压缩包不包含 `_build/`、`work/` 或机器状态，也不
向 Mooncakes 或其他注册表上传：

```sh
python3 scripts/build_source_archive.py --output-dir dist
python3 scripts/release_smoke_test.py dist/moonjmap-0.1.0-src.tar.gz
python3 scripts/release_smoke_test.py dist/moonjmap-0.1.0-src.zip
```

归档根目录内的 `RELEASE-MANIFEST.json` 保存每个源文件的字节数和 SHA-256。
同一源码树重复构建时，tar.gz 和 ZIP 的成员顺序、时间戳和归属字段保持
稳定；如果其他工作正在修改源码，必须等树冻结后再比较归档哈希。smoke
测试会在临时目录解包，验证路径安全、清单完整性、Python wire 导入、固定
wire 回归、向量回放和 codec round-trip。

## 证据边界

本仓库中的 fixture、模型回放和测试输出证明的是模型内部行为；真实 JMAP 服务兼容和性能以 [真实服务验证报告](https://github.com/001-Elsa/jmap-mbt/blob/main/outputs/MoonJMAP-%E7%9C%9F%E5%AE%9E%E6%9C%8D%E5%8A%A1%E4%BA%92%E6%93%8D%E4%BD%9C%E4%B8%8E%E6%80%A7%E8%83%BD%E9%AA%8C%E8%AF%81-2026-10-26.md) 及其脱敏 JSON 为准。该报告只覆盖 Stalwart v0.16.27 的本机临时部署、Basic Auth 和合成数据，不扩展为其他服务、TLS/OAuth 或生产性能保证。

