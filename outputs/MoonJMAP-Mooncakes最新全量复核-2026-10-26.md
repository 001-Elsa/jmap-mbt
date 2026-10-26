# MoonJMAP 与 Mooncakes.io 当前公开目录复核（2026-10-26）

本报告刷新 2026-10-25 报告的公开快照，固定了本次读取的原始 JSON、SHA-256、增量 ZIP、manifest checksum 和源码静态扫描结果。扫描不执行第三方代码。

## 结论

截至本次快照，`/api/v0/modules/` 返回 **3331 个模块版本条目**；相对 2026-10-25 的 3,321 条，新增 **10** 条、已有模块版本变化 **17** 条，共重新获取并扫描 **27 个当前版本包**。

对这 27 个新增/变化包：

- ZIP 下载：27/27 成功；失败：0。
- manifest 校验：27/27 匹配；失败：0。
- 当前版本覆盖：3331/3331；由 3,304 个既有全量源码记录、2026-10-25 增量当前版本和本次 27 个增量当前版本按精确 `(name, version)` 合并得到。
- 新增/变化包中没有出现 JMAP token、JMAP capability URN、JMAP Mail 方法签名或 JMAP wire 标记。

这支持以下有限结论：

> 在 2026-10-26 这次公开目录和可读取发布 ZIP 快照、以及本报告列出的扫描方法下，未观察到以 JMAP 邮件查询双状态协调、排序敏感连续前缀补位和 JMAP 专属前缀转移证明为主要交付的同目的 Mooncakes 模块。

它不支持“完全空白原创”“与所有项目不相似”，也不等于已经完成对赛事全部参赛项目的源码比对。

## 快照证据

- 抓取时间（Asia/Shanghai）：`2026-10-26T08:58:08–08:58:10+08:00`（原始接口文件的本地 mtime 窗口）。
- `modules/` 原始响应 SHA-256：`3e086048fc1dbffd5b9fa5a01eaf5c56b8e1c983cb7e1856440f10600f2cd57e`。
- `modules/` 原始字节数：1189586。
- statistics：`{"total_modules": 3331, "total_packages": 29532, "total_lines": 51689542, "total_downloads": 9948062}`；原始 SHA-256：`1a81597d08065767557a04ee38e46017e27fc635f13ce81e7ffadb0bfaaac46f`。
- `search?kw=jmap`：`[]`；原始 SHA-256：`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`。
- `search?kw=queryChanges`：`[]`；原始 SHA-256：`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`。

统计接口的下载量是站点实时计数，可能在不同读取时刻变化；因此报告同时保存原始 JSON 和 SHA-256。

## 本次 27 个增量包

### 新增 10 个

- `huanguan-Q/typesafe-sdk-moonbit@0.2.0`：Community MoonBit SDK for TypeSafe System One (Jev): typed Noul/Choice/Score questions, formally verified confidence gates and retry policy, and network-free testing.
- `moonbit-community/tree-sitter-make@0.101.1`：Makefile grammar for tree-sitter (tree-sitter-grammars/tree-sitter-make v1.1.1), for the MoonBit port of Tree-sitter (moonbit-community/treesitter).
- `moonbit-community/tree-sitter-regex@0.100.0`：regex grammar for tree-sitter (tree-sitter/tree-sitter-regex v1.0.0), for the MoonBit port of Tree-sitter (moonbit-community/treesitter).
- `moonbit-community/tree-sitter-verilog@0.100.3`：Verilog grammar for tree-sitter (tree-sitter/tree-sitter-verilog v1.0.3), for the MoonBit port of Tree-sitter (moonbit-community/treesitter).
- `moonbit-community/tree-sitter-zig@0.101.2`：Zig grammar for tree-sitter (tree-sitter-grammars/tree-sitter-zig v1.1.2), for the MoonBit port of Tree-sitter (moonbit-community/treesitter).
- `moonrockz/bpmn@0.2.0`：Portable BPMN document reading, writing and traversal
- `moonrockz/diagrams-animated@0.2.0`：Standalone illustrative diagram playback for diagrams.mbt
- `moonrockz/diagrams-bpmn@0.2.0`：BPMN document adapter for diagrams.mbt
- `nawei123/runledger@0.2.0`：Offline integrity checks and token accounting for agent run logs
- `tc-adventureking/ipset@0.2.1`：Pure MoonBit IPv4/IPv6 address sets and minimal CIDR covers

### 版本变化 17 个

- `JQ-ai-nb/relcore`：`0.2.5` → `0.2.6`；A general relational execution core for MoonBit: typed plans, per-node cardinality, and verifiable contracts with minimal witnesses.
- `justinwongcn/moon-ical`：`0.2.0` → `0.4.0`；iCalendar (RFC 5545) parsing, recurrence expansion, and a minimal CalDAV server in pure MoonBit
- `justinwongcn/moonpgp`：`0.1.0` → `0.3.0`；Pure-MoonBit OpenPGP implementation (RFC 4880/9580): email encryption, decryption, signing and verification, interoperable with GnuPG and gopenpgp.
- `Lampese/mathplotlib`：`0.13.0` → `0.17.0`；A MoonBit plotting library with SVG output.
- `mldong/moon-file-storage-cos`：`0.1.1` → `0.1.2`；Tencent Cloud COS platform adapter for moon-file-storage
- `mldong/moon-file-storage-obs`：`0.1.1` → `0.1.2`；Huawei Cloud OBS platform adapter for moon-file-storage
- `mldong/moon-file-storage-oss`：`0.1.1` → `0.1.2`；Alibaba Cloud OSS platform adapter for moon-file-storage
- `mldong/moon-file-storage-qiniu`：`0.1.2` → `0.1.3`；Qiniu Kodo platform adapter for moon-file-storage
- `mldong/moon-file-storage-verify`：`0.1.6` → `0.1.7`；Shared platform contract suite for moon-file-storage
- `moonrockz/diagrams`：`0.1.0` → `0.2.0`；Diagramming for MoonBit: Mermaid, PlantUML, Draw.io, Graphviz DOT and more
- `moonrockz/diagrams-mermaid`：`0.1.0` → `0.2.0`；Mermaid for diagrams.mbt: lossless CST, parser, AST, printer and conversion to diagram models
- `moonrockz/diagrams-svg`：`0.1.0` → `0.2.0`；Standalone SVG rendering for diagrams.mbt models, in the visual style of archify
- `PingGuoMiaoMiao/moonlsm`：`0.2.0` → `0.2.1`；Embedded LSM-tree storage engine for MoonBit
- `riantr/moonbit_doubleML`：`0.164.37` → `0.164.41`；Pure-MoonBit port of doubleml-for-py: Double / Debiased Machine Learning for partial linear, IRM, IV, DID, SSM, APO(S), PQ, QTE, LPQ, CVaR, RDD, BLP, and policy-tree models
- `sundaysebasidian-byte/moonabnf`：`0.2.1` → `0.3.0`；Byte-oriented ABNF grammar AST, validation, budgeted recognition and input derivation trees
- `sundaysebasidian-byte/moonstomp`：`0.2.1` → `0.3.1`；Bounded incremental STOMP 1.0/1.1/1.2 codec and transport-independent client
- `vitro/engine`：`0.8.0` → `0.9.0`；MoonBit implementation of the Vitro C teaching engine: 156 diagnostic codes, 151 opcodes, full AST family, byte-exact against Clang-golden and frozen digest baselines

## 候选源码复核

本次增量扫描同时保留宽召回信号。宽信号不能单独证明 JMAP 实现；逐个检查了命中上下文。

- `justinwongcn/moon-ical@0.4.0` 的 `result_of` 命中位于 `ical/rrule/expand_test.mbt`，是 iCalendar RRULE 测试辅助函数；没有 JMAP、`Email/query`、`queryState` 或 JMAP capability。
- `justinwongcn/moonpgp@0.3.0` 的大量 mail 命中来自 OpenPGP/SMTP/IMAP/email 领域，是邮件安全与邮件传输项目，不是 JMAP Mail 查询同步。
- `mldong/moon-file-storage-verify@0.1.7` 的 `download_url` 命中是对象存储预签名 URL 合同测试，不是 JMAP session/blob URL。
- `moonrockz/bpmn`、`diagrams*` 的 `EventSource`/`pop` 命中属于 XML/图形解析或栈操作；没有 JMAP StateChange。
- 其余新增/变化包的命中是 MIME、`pop`、`pending`、STOMP、HTTP Authorization 等低特异文本。

严格高特异筛查检查：`jmap`、`urn:ietf:params:jmap`、JMAP Core/Mail 方法名、`methodCalls/methodResponses`、`resultOf`/`ifInState`/`cannotCalculateChanges` 组合、`queryState`、`Email/queryChanges` 等。`result_of` 单独出现只作为低特异信号保存，不作为 JMAP 命中。

## 当前范围不能证明什么

- Mooncakes `/api/v0/modules/` 是公开注册表，不是赛事报名清单；没有公开赛事 roster、仓库 commit/ref 或提交包，就不能声称已比对“赛事全部参赛项目”。
- 本次使用公开发布 ZIP 和既有 2026-10-25 的全量当前版本扫描记录；没有对 Mooncakes Git index 中全部历史版本逐包重扫。
- 静态文本筛查和候选上下文复核不能证明不存在语义等价实现、未发布实现、私有实现、代码复制或法律层面的原创性。
- 不能据此保证赛事评审不会判定相似。比赛仍应核对章程，并按评审方提供的参赛项目清单逐项保留证据。

## 可复核文件

- `work/live-scan-2026-10-26/modules-live.json`
- `work/live-scan-2026-10-26/statistics.json`
- `work/live-scan-2026-10-26/search-jmap.json`
- `work/live-scan-2026-10-26/search-queryChanges.json`
- `work/live-scan-2026-10-26/selection.json`
- `work/live-scan-2026-10-26/download-results.json`
- `work/live-scan-2026-10-26/manifest-delta.json`
- `work/live-scan-2026-10-26/scan-delta.json`
- `work/live-scan-2026-10-26/current-source-coverage.json`
- `work/live-scan-2026-10-26/snapshot-report.json`
- `work/live-scan-2026-10-26/download_delta.py`
- `work/live-scan-2026-10-26/verify_manifests.py`
- `work/live-scan-2026-10-26/scan_delta.py`

## 与 MoonJMAP 定位的边界

必须继续把 HTTP、JSON、通用状态机、集合对账、checkpoint、trace、证书、邮件模型和 SMTP/IMAP/POP3 等列为邻近或支撑能力。可主张的差异仍然是 JMAP 专属组合：同账号 Email state 与 queryState 分链、`Email/changes` 与 `Email/queryChanges` 协调、同 queryState 的连续有序前缀补位、`Email/get` 按 ID 归位、完整对象门禁和 JMAP 专属前缀转移证明。

本报告没有执行任何第三方包代码，没有把 README 单独当作实现证明，也没有进行 Git/赛事提交或发布操作。
