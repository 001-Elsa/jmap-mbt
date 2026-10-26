# MoonJMAP 与 Mooncakes.io 公开全量源码核查（2026-10-26）

本报告只覆盖 Mooncakes.io 当前公开注册表中可读取的发布 ZIP，不是赛事报名清单。它合并 2026-10-25 的 3,304 包全量静态源码核查与 2026-10-26 新增/变更的 27 包，覆盖当前 3,331 个精确模块版本。

## 结论

- 当前公开目录条目数：3331；目录原始 JSON SHA-256：3e086048fc1dbffd5b9fa5a01eaf5c56b8e1c983cb7e1856440f10600f2cd57e。
- 全量协议特征源码扫描覆盖：3304 个旧快照包 + 27 个当日增量包 = 3331 个当前条目。
- 全量 JMAP capability URN 命中：0；标准 JMAP Mail 方法签名命中：0。
- 在公开快照和静态方法下，没有观察到可直接替代 MoonJMAP JMAP Core/Mail 交付的协议文本证据；这不是语义等价、代码原创性或赛事判重保证。

> 这里的“全量”指公开注册表的当前发布坐标和已读取源码证据。历史版本、未发布源码、私有仓库以及赛事提交不在范围内。

## 证据范围

| 项目 | 数值 | 证据 |
|---|---:|---|
| 当前目录条目 | 3331 | work/live-scan-2026-10-26/modules-live.json；SHA-256 3e086048fc1dbffd5b9fa5a01eaf5c56b8e1c983cb7e1856440f10600f2cd57e |
| 2025 全量发布 ZIP | 3304 | 官方 checksum 一致 3304/3304 |
| 2025 全量可读文本 | 302874 | 总字节 3868145720 |
| 2025 MoonBit 文件 | 147490 | 静态读取，不执行 |
| 2026-10-26 增量 ZIP | 27 | manifest/ZIP 27/27 |
| 当前源码记录覆盖 | 3331/3331 | work/live-scan-2026-10-26/current-source-coverage.json |

## 方法边界

旧快照的全量方法对每个发布 ZIP 的每个可读文件计算 SHA-256，并使用保守协议特征模式保存命中上下文；高召回候选再做人工语义复核。它回答“是否出现 JMAP 专属词法/接口证据”，不能回答任意重命名或重排后的语义等价。

本次另对 27 个当日 ZIP 运行 scripts/source_similarity_audit.py，计算 20-token 精确/形状归一化 winnowing、规范化源码行和声明签名。旧 3,304 包的归档正文没有保留在当前工作区，因此没有把这套通用 token 指纹倒推到 3,331 个包；下表只能作为 27 包增量补充。

## 27 个增量包的 token 相似度补充

- 候选 ZIP：27；处理错误：0。
- 机器报告：outputs/mooncakes-delta-source-similarity-2026-10-26/audit.json；SHA-256：e825c7e81df123968579658a7dbd6895cf8a65bfbf433036d7148c3bfbc2b967。

| 包 | 精确 token 包含率 | 形状 token 包含率 | 规范行包含率 | 分流分数 |
|---|---:|---:|---:|---:|
| vitro__engine@0.9.0--5a61c4cab9 | 0.0006 | 0.0408 | 0.0081 | 0.0123 |
| Lampese__mathplotlib@0.17.0--6324cb619c | 0.0004 | 0.0349 | 0.0074 | 0.0104 |
| moonrockz__bpmn@0.2.0--478e827b84 | 0.0001 | 0.0183 | 0.0034 | 0.0065 |
| justinwongcn__moonpgp@0.3.0--9f8817ff1b | 0.0001 | 0.0204 | 0.0027 | 0.0060 |
| moonrockz__diagrams-svg@0.2.0--c464356bf4 | 0.0001 | 0.0144 | 0.0024 | 0.0047 |
| justinwongcn__moon-ical@0.4.0--8104600212 | 0.0002 | 0.0125 | 0.0037 | 0.0043 |
| sundaysebasidian-byte__moonstomp@0.3.1--83964d1135 | 0.0009 | 0.0079 | 0.0081 | 0.0043 |
| moonrockz__diagrams-mermaid@0.2.0--7e6d42ef45 | 0.0005 | 0.0095 | 0.0044 | 0.0040 |
| moonrockz__diagrams@0.2.0--ec707cb9a4 | 0.0001 | 0.0122 | 0.0014 | 0.0040 |
| riantr__moonbit_doubleML@0.164.41--8f24c977b9 | 0.0000 | 0.0153 | 0.0007 | 0.0040 |
| sundaysebasidian-byte__moonabnf@0.3.0--d2b7d97d0b | 0.0002 | 0.0073 | 0.0047 | 0.0032 |
| huanguan-Q__typesafe-sdk-moonbit@0.2.0--a9066fb0fd | 0.0000 | 0.0087 | 0.0014 | 0.0027 |
| PingGuoMiaoMiao__moonlsm@0.2.1--2164e2e106 | 0.0000 | 0.0068 | 0.0017 | 0.0023 |
| nawei123__runledger@0.2.0--a2bd1dc757 | 0.0002 | 0.0055 | 0.0024 | 0.0023 |
| JQ-ai-nb__relcore@0.2.6--345cfe04ba | 0.0000 | 0.0058 | 0.0010 | 0.0020 |
| tc-adventureking__ipset@0.2.1--78e4ab29c7 | 0.0000 | 0.0047 | 0.0003 | 0.0012 |
| moonrockz__diagrams-bpmn@0.2.0--d6aed7e8bc | 0.0000 | 0.0030 | 0.0003 | 0.0008 |
| mldong__moon-file-storage-obs@0.1.2--acad0a01dc | 0.0000 | 0.0024 | 0.0003 | 0.0007 |
| mldong__moon-file-storage-cos@0.1.2--914fd941c9 | 0.0000 | 0.0025 | 0.0000 | 0.0006 |
| mldong__moon-file-storage-oss@0.1.2--79484e25a1 | 0.0000 | 0.0024 | 0.0000 | 0.0006 |
| mldong__moon-file-storage-qiniu@0.1.3--1dc3a1719e | 0.0000 | 0.0018 | 0.0000 | 0.0004 |
| mldong__moon-file-storage-verify@0.1.7--69e2ac6245 | 0.0000 | 0.0011 | 0.0003 | 0.0004 |
| moonbit-community__tree-sitter-verilog@0.100.3--f6d3d8a5d3 | 0.0001 | 0.0001 | 0.0000 | 0.0001 |
| moonbit-community__tree-sitter-make@0.101.1--f81367eef9 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| moonbit-community__tree-sitter-regex@0.100.0--1161ceda47 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| moonbit-community__tree-sitter-zig@0.101.2--377177b30a | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| moonrockz__diagrams-animated@0.2.0--0b37f68728 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

分流分数只是人工复核排序信号。公共语言结构、测试样板、依赖接口和独立实现都可能造成交集；本报告没有把任何分数解释为抄袭或原创结论。

## 全量信号汇总

| 信号 | 2025 全量命中次数 / 包数 | 2026 增量命中次数 / 包数 |
|---|---:|---:|
| jmap | 105 / 7 | 0 / 0 |
| rfc862x | 494 / 53 | 0 / 0 |
| capability_urn | 0 / 0 | 0 / 0 |
| jmap_wire | 161 / 21 | 0 / 0 |
| jmap_reference_state | 361 / 19 | 5 / 1 |
| jmap_mail_methods | 0 / 0 | 0 / 0 |
| jmap_mail_fields | 4754 / 135 | 9 / 1 |
| mail_protocol | 50820 / 1152 | 826 / 15 |
| mail_domain | 19610 / 463 | 70 / 2 |
| json_rpc | 7866 / 122 | 0 / 0 |
| json_pointer | 4788 / 94 | 0 / 0 |
| sse | 1188 / 101 | 9 / 1 |
| http_adapter | 17585 / 441 | 15 / 4 |

## 不可证明的事项

- Mooncakes 公共注册表不等于任何赛事的完整参赛名单；没有官方 roster、仓库 URL、commit/ref 或提交归档，就不能声称比对了赛事全部项目。
- 静态词法信号与有限 token 指纹不能证明不存在语义等价实现、独立重写、未发布实现、私有实现或代码复制。
- 没有执行任何第三方包，也没有把 README 单独当成实现证明；ZIP 路径、官方 manifest checksum 和扫描 JSON 均保留供复核。
- 赛事判重仍由章程和评审方决定。

## 可复核入口

- work/live-scan-2026-10-26/modules-live.json
- work/live-scan-2026-10-26/current-source-coverage.json
- work/live-scan-2026-10-26/scan-delta.json
- outputs/MoonJMAP-源码核查证据-2026-10-25.zip（3,304 包全量静态证据）
- outputs/mooncakes-delta-source-similarity-2026-10-26/audit.json（27 包 token 补充）
- scripts/source_similarity_audit.py
