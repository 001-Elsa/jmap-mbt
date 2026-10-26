# MoonJMAP 与 Mooncakes.io 最新全量目录复核报告（2026-10-25）

本目录保存一次在 2026-10-25（Asia/Shanghai）对 Mooncakes.io 的新鲜公开目录复核。快照接口使用带结尾 `/` 的公开路径 `https://mooncakes.io/api/v0/modules/`；无结尾 `/` 在本次读取时返回 404。`modules-live.json` 是原始模块列表，`statistics.json` 是统计接口原始返回，`search-jmap.json` 与 `search-queryChanges.json` 是公开搜索接口原始返回。

## 结果

- 当前目录：3,321 个模块；统计接口：29,494 个 packages、51,575,380 行、9,929,734 次下载（统计值随站点变化）。
- 当前目录快照 SHA-256：`85f0bebf00db24ce9857465a7e3cd4becde2965caa6fc139a261711cabe646d1`。
- `search?kw=jmap`：空数组；`search?kw=queryChanges`：空数组。
- 相对前一份 3,304 模块源码快照：17 个新模块、23 个最新版本变化；对这 40 个当前版本逐包下载并扫描，40/40 的 ZIP SHA-256 与对应 manifest `metadata.checksum` 相等。
- 旧快照的 3,304 个发布包扫描结果与本次 40 个增量包合并后，按当前 `(name, version)` 覆盖 3,321/3,321 个当前目录模块；没有遗漏当前模块。
- 增量包的 JMAP 高特异标记（`jmap`、`urn:ietf:params:jmap`、JMAP Mail 方法名、`resultOf`、`ifInState`、`queryState`、`cannotCalculateChanges` 等）没有召回模块。`apoloe4/moonreconcile` 的 `SessionState`/表格数字等是通用集合对账实现的词面误报，源码没有 JMAP Mail 方法或状态链。

## 当前增量清单

### 新增 17 个模块

`Lyhdsba/fusekite`、`Mr-Shi123/moondynamo`、`OJII3/moq-mbt`、`V1GreenSummer/paddleocr`、`apoloe4/moonreconcile`、`btlqql/moon_bpflab`、`btlqql/moon_card`、`btlqql/moon_diag`、`conglinyizhi/dsh-console-backend`、`conglinyizhi/dsh-console-frontend`、`guo-dong-123/moon-trace`、`hp0200/moonbit-sparse-math`、`moonbitstack/moonnum`、`moonbitstack/moonuuid`、`pei0331/moon-accesslog`、`xiaoxiao1211/moon-accesslog`、`zyyaa125/edgeweaver`。

其中最接近 MoonJMAP 主题的是 `apoloe4/moonreconcile@0.2.0`：它是基于 IBLT 的 transport-neutral 集合对账与可逆 sketch，处理稳定 ID 集合的编码、交换和解码；它不包含 JMAP `Email/changes`、`Email/queryChanges`、opaque query state、邮件属性、排序前缀或 Email/get 补位。其源码扫描中命中的 `SessionState` 与 benchmark 数字属于普通状态/数值文本，不是 JMAP 协议证据。`zyyaa125/edgeweaver@0.1.0` 是弱网络 edge device 管理平台，虽有 offline-first 描述，但没有邮件、JMAP 或查询视图语义。其余新增包分别属于 DynamoDB、MoQ/QUIC、OCR、BPF、APDU/EMV、UDS/OBD、控制台、trace、稀疏数学、数值/UUID、日志分析等领域。

### 23 个版本变化

`404-32/moon-pe-inspect 0.5.0→0.6.0`、`Freon793/moonopt 0.3.0→0.4.0`、`JQ-ai-nb/relcore 0.2.4→0.2.5`、`Lampese/mathplotlib 0.7.0→0.13.0`、`MuVirus/moonfig 0.1.2→0.1.3`、`SongYZZZ/moon-liberty 0.2.0→0.3.0`、`cjyhjy/uri_template 0.5.0→0.5.1`、`cli/column 0.1.3→0.1.4`、`cli/core 0.8.0→0.8.1`、`cli/csplit 0.2.0→0.2.1`、`cli/diff 0.2.0→0.2.1`、`cli/rev 0.1.3→0.1.4`、`cli/sort 0.2.2→0.2.3`、`cli/split 0.1.2→0.1.3`、`cli/tac 0.1.3→0.1.4`、`kupas/pm3 0.1.7→0.1.8`、`liyun6666/moon-ipp 0.1.3→0.1.4`、`mhlagent/sheetsentry 0.5.0→0.6.0`、`prowk/mooncql 0.2.0→0.2.1`、`riantr/moonbit_doubleML 0.164.36→0.164.37`、`sa2360/pddl 0.1.1→0.2.0`、`superbigcup325/colenc 0.1.0→0.1.1`、`wdgodghl/moonwren 0.5.0→0.6.0`。逐包当前发布载荷均已重新读取并做高特异标记扫描；没有发现 JMAP Mail 交付。

## 和 MoonJMAP 的实际边界

`apoloe4/moonreconcile` 是必须披露的相邻项目：它使“集合差异恢复、同步计划、transport-neutral、状态机”这些词不能作为 MoonJMAP 的独有卖点。MoonJMAP 的可辩护差异必须落在具体 JMAP 语义：同账号中 Email state 与 queryState 分链、`Email/changes` 与 `Email/queryChanges` 协调、有序查询前缀补位、按 ID 归位 `Email/get`、`cannotCalculateChanges` 后的受控重建和带能力约束的 checkpoint 恢复。

新目录中未出现直接 JMAP 项目，但这只支持“本快照和记录方法下未观察到同目的 JMAP Mail 视图同步实现”，不支持“完全不重合”“绝对原创”“全球首创”或赛事不判重。HTTP、JSON、状态机、集合差异、checkpoint、离线恢复、邮件领域和通用增量计算仍然存在真实邻近项目。

## 可复核文件

- `snapshot-report.json`：机器可读快照、增量清单、覆盖率和高特异筛查结果。
- `modules-live.json`：3,321 条目录原始响应。
- `statistics.json`、`search-jmap.json`、`search-queryChanges.json`：原始公开接口响应。
- `download-results.json`：40 个新增/变更版本下载记录和 SHA-256。
- `manifest-delta.json`：40 个 manifest checksum 对照，40/40 匹配。
- `scan-delta.json`：40 个发布 ZIP 的全文本静态扫描及命中行。
- `download_delta.py`、`verify_manifests.py`、`scan_delta.py`：可重复执行的增量获取、哈希核对和扫描脚本。

## 方法限制

本次扫描读取的是 Mooncakes 当前公开目录和公开发布 ZIP；没有执行第三方包代码，也没有把仓库 README 当作实现证明。旧快照的全量源码结果来自前一轮 3,304 包审计，本轮对目录新出现或版本变化的 40 个包进行了补扫。目录、版本和发布载荷可能继续变化；在发布或参赛前需要重新抓取目录、重新记录哈希并复核邮件/同步/状态候选。一次静态快照不能证明未发布代码不存在、语义等价实现不存在、法律原创性成立或评审方不会判定相似。
