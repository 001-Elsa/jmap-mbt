# Git 仓库导入说明

日期：2026-10-26（Asia/Shanghai）。目标仓库：[001-Elsa/jmap-mbt](https://github.com/001-Elsa/jmap-mbt)。

整理前，本地目录与目标仓库均没有 Git 提交历史。本次按功能依赖、文件创建时间和最后修改时间，把既有源码快照整理为 20 次非空提交。所有提交使用实际整理时刻，没有倒填作者日期或提交日期。文件时间只用于辅助排序，不能证明曾存在对应的中间代码版本。

文件最初创建于 2026-10-25，实现、修复与复核延续到 2026-10-26。排序先保证依赖和可评审范围，再参考同一功能的文件时间。例如，同步内核先于边界回归和位置证书，完整源码文档先于归档工具。每次提交说明列出导入前已观察到的文件修改时间范围。

## 提交内容

| Order | Commit | Files |
| --- | --- | ---: |
| 01 | chore: initialize MoonBit package, license and repository exclusions | 5 |
| 02 | test: add RFC fixtures and independent sync oracle | 3 |
| 03 | feat(email): define fixed query views and email projections | 4 |
| 04 | feat(jmap): add typed MoonBit requests and responses | 4 |
| 05 | refactor(python): retain legacy sync model for migration | 2 |
| 06 | feat(wire): add Python codec and read-only HTTP probe | 8 |
| 07 | docs(examples): add vector replay and codec demonstrations | 4 |
| 08 | feat(sync): implement two-state prefix synchronization and recovery | 3 |
| 09 | test(sync): cover bound responses and error acceptance | 2 |
| 10 | test(sync): exhaust prefix boundaries and final-rank merging | 2 |
| 11 | feat(certificate): add positional witnesses and offline verification | 4 |
| 12 | test(differential): compare MoonBit and Python event traces | 7 |
| 13 | feat(metrics): add synthetic traces and deterministic counters | 21 |
| 14 | feat(interop): add live read-only benchmark and redacted records | 17 |
| 15 | feat(audit): add public source inventory and similarity tools | 5 |
| 16 | docs(sync): specify state contracts, recovery and support limits | 3 |
| 17 | test(validation): add acceptance matrix and evidence generator | 5 |
| 18 | docs: complete project guide, changelog and import notes | 4 |
| 19 | build: add deterministic archives and clean extraction smoke checks | 2 |
| 20 | docs(audit): preserve redacted planning and source-review evidence | 30 |

## 公开范围与历史证据

上传正式源码、测试、示例、工具、文档和许可证，并通过 `.gitignore` 的精确白名单保留 `outputs/` 内经过检查的 62 份 Markdown/JSON。`work/` 中的第三方源码与本地调查材料、`_build/`、`dist/`、缓存、调查用 ZIP/HTML/CSV 和机器凭据不随仓库上传，原文件继续留在本地。

历史报告保留当时的结论、快照数量、源归档哈希和验证边界。其中“未提交 Git”“未上传”等措辞描述报告形成时的状态；公开仓库状态由本次导入记录更新。报告正文中的 `work/...` 与旧机器绝对路径是历史来源引用，未作为公开源码或可复现环境交付。真实服务记录保留原日期，本次本地回归不会把它们改写为新的实服验证。

公开证据的 6 份 JSON 做了发布脱敏：URL 认证查询参数与 userinfo 替换为 `REDACTED`，来源提取器误收集的 1,097 个非 URL 或污染片段替换为 `[omitted: non-URL source clue]`。原始比较统计、结论、数组长度和被比较源归档的 SHA-256 保持原义。报告链接只做便携性整理。脱敏后的报告字节与原始扫描输出可能不同，不能把历史报告哈希误读成公开副本的字节哈希。

源码压缩包沿用正式目录白名单，不包含 `outputs/` 历史证据；这些证据从 GitHub 仓库访问。

## 本次上传前验证

- MoonBit `wasm`：86/86；`wasm-gc`：86/86；`native` 静态检查通过。
- 排名归并测试覆盖 93,072 组；证书测试覆盖 4,225 种有序子集转移。
- Python 回归：26/26；独立 oracle：17/17；固定向量：15/15；MoonBit/Python 逐步对拍：15/15。
- 归档检查入口：`python3 scripts/build_source_archive.py --output-dir dist/github-upload-2026-10-26`，再分别对 tar.gz 与 ZIP 执行 `scripts/release_smoke_test.py`。

以上结果是本地代码和固定输入的验证。本次没有重新连接 Stalwart 或其他真实邮箱服务，没有发布 Mooncakes 包或提交赛事。
