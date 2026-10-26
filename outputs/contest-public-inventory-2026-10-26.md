# 2026 MoonBit 黑客松公开候选盘点与源码可复核记录

盘点时间：2026-10-26T09:14:49.315740+08:00  
项目：`/Users/hanzhen09/Desktop/jmap`

## 结论

目前仍不能声称已完成赛事“全部参赛项目”的源码比对。公开官网与报名表提供了规则和提交入口，但本次读取没有发现官方报名、审核通过或最终参赛项目清单，也没有源码提交快照。此次盘点把可从公开 GitHub 搜索、既有公开候选记录和 Mooncakes 元数据中发现的项目固定为 **31 个候选**，其中 **31/31 成功读取源码、0 个审计读取错误**。这些项目属于“公开可发现候选”，不等于官方参赛 roster。

在本次固定的 31 个仓库 HEAD 和审计方法下，所有候选的高特异 `JMAP` 语义特征计数均为 0；源码审计也没有给出达到直接重合判定标准的信号。该结果只能说明当前公开候选快照中未观察到 JMAP 邮件查询实现关键词或强词法/结构重合，不能排除改名实现、语义等价、未公开项目或赛事最终提交版本差异。

机器可读清单：[contest-public-inventory-2026-10-26.json](contest-public-inventory-2026-10-26.json)  
候选清单：contest-source-manifest-expanded.json (`work/contest-2026-10-26/public-candidates/contest-source-manifest-expanded.json`; local-only evidence)  
源码审计：[audit.md](contest-source-audit-public-candidates-expanded/audit.md) / [audit.json](contest-source-audit-public-candidates-expanded/audit.json)

## 外部来源与抓取证据

| 来源 | 本次状态 | 证据 |
|---|---|---|
| `website_html` | HTTP 200, 1311 bytes, SHA-256 `75fb92b0c38c7318ab5fe7edf6b6376a157cc3881dcbf3430ee2480505e2a40b` | [https://moonbitlang.github.io/Hackathon2026/](https://moonbitlang.github.io/Hackathon2026/) |
| `website_js` | HTTP 200, 239411 bytes, SHA-256 `6c5b682ea57057e39d2a859bc03d41087ebb40876e9d5bd5941793a8bf91164b` | [https://moonbitlang.github.io/Hackathon2026/assets/index-Cb3Bwakq.js](https://moonbitlang.github.io/Hackathon2026/assets/index-Cb3Bwakq.js) |
| `registration_form` | HTTP 200, 782895 bytes, SHA-256 `e6b1aad2dd3adbe23bfae2cc51c39456d43b5a7ad95022e7a5c1162b0fca3ca8` | [飞书公开报名表](https://bxup9uklfcb.feishu.cn/share/base/form/shrcnWUMlgpbwHaXgzV7HmNhNhg)（响应最终 URL 带临时 auth_token） |
| `charter` | 读取失败：HTTP 302 重定向循环 | [飞书正式章程](https://bxup9uklfcb.feishu.cn/wiki/Dx4Bwd6D1i3GfHkajQCcF7SznEd) |
| `mooncakes_modules` | HTTP 200, 1189586 bytes, SHA-256 `71bfcb5408af46f05a8cda3b5c195d93cc1509cd39a56bc517392dd86e37c188` | [https://mooncakes.io/api/v0/modules/](https://mooncakes.io/api/v0/modules/) |
| `mooncakes_search_jmap` | HTTP 200, 2 bytes, SHA-256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | [https://mooncakes.io/api/v0/search?kw=jmap](https://mooncakes.io/api/v0/search?kw=jmap) |
| `mooncakes_search_queryChanges` | HTTP 200, 2 bytes, SHA-256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | [https://mooncakes.io/api/v0/search?kw=queryChanges](https://mooncakes.io/api/v0/search?kw=queryChanges) |
| `github_repo_search_moonbit_hackathon_2026` | HTTP 200, 65400 bytes, SHA-256 `a1c70be40ae02639d26b170d6440da8f3421238dad2310147f997ea862894b56` | [https://api.github.com/search/repositories?q=MoonBit+hackathon+2026&per_page=100](https://api.github.com/search/repositories?q=MoonBit+hackathon+2026&per_page=100) |
| `github_repo_search_moonbit_hackathon` | HTTP 200, 129895 bytes, SHA-256 `54accffacb1afe65430a3eaed032738af9ad1fba7fa0c11f1059852629f3bb40` | [https://api.github.com/search/repositories?q=MoonBit+hackathon&per_page=100](https://api.github.com/search/repositories?q=MoonBit+hackathon&per_page=100) |
| `github_repo_search_moonbit_黑客松` | HTTP 200, 10724 bytes, SHA-256 `b35b78bc555dea475e6feda3783b8cb614cb8bfdd72e71257dc79add74ce395d` | [https://api.github.com/search/repositories?q=MoonBit+%E9%BB%91%E5%AE%A2%E6%9D%BE&per_page=100](https://api.github.com/search/repositories?q=MoonBit+%E9%BB%91%E5%AE%A2%E6%9D%BE&per_page=100) |

抓取原始文件和哈希清单：live-refresh-20261026/fetch-manifest.json (`work/contest-2026-10-26/live-refresh-20261026/fetch-manifest.json`; local-only evidence)；报名表/章程的单独抓取记录见 fetch-manifest.json (`work/contest-2026-10-26/fetch-manifest.json`; local-only evidence)。GitHub 仓库搜索返回去重后 25 个仓库（含官网仓库），排除官网源码仓库后纳入 10 个新候选；与先前 21 个公开候选合并为 31 个。`/api/v0/modules/` 返回 3331 条模块版本条目，且 `search?kw=jmap` 与 `search?kw=queryChanges` 均返回 `[]`。Mooncakes 是公开包注册表，不能替代赛事名单。

## 公开候选与源码状态

状态说明：`source=ok` 表示清单路径存在、HEAD 与清单一致，并被源码审计成功读入；它不表示已确认报名或获奖。`JMAP` 列来自审计器的高特异语义特征计数，不是完整语义证明。

| 候选仓库 | 公开发现线索 | 固定 HEAD | 源码状态 | 树 SHA-256（前 16 位） | 源码字节/行 | JMAP 特征 |
|---|---|---|---|---:|---:|---:|
| [17731189258/sbs](https://github.com/17731189258/sbs) | MoonBit hackathon | `fba3f6520f5185deac7d19ad84d815b0f57a9160` | `ok` | `4c9317ca37a80604` | 93,670 / 3,626 | 0 |
| [2892480843/moonyaml](https://github.com/2892480843/moonyaml) | MoonBit hackathon | `65d2da65cbd5be3410e864c40287ead513f85d5f` | `ok` | `43e947e32f428c07` | 75,589 / 2,991 | 0 |
| [CodeAIKai/agent-tape](https://github.com/CodeAIKai/agent-tape) | MoonBit hackathon 2026, MoonBit hackathon | `959c9010bfc3e8fdb7f53d0b36b2d546ff35e583` | `ok` | `6b4edbdcfc417e73` | 310,673 / 7,318 | 0 |
| [FidollarinLA/moondata-lab](https://github.com/FidollarinLA/moondata-lab) | MoonBit hackathon | `0e430b978bf4742e64c85fe48fb3c02d10b6f6d2` | `ok` | `ae75cb8a4e4a59f4` | 343,604 / 5,905 | 0 |
| [forey217/moonconfig](https://github.com/forey217/moonconfig) | MoonBit hackathon 2026, MoonBit hackathon | `72248b020c8cce7aaae1f9d7ebad625443aab2b3` | `ok` | `78ea8b7065b713d0` | 118,595 / 3,246 | 0 |
| [funvtion/moonpack-lens](https://github.com/funvtion/moonpack-lens) | MoonBit hackathon 2026, MoonBit hackathon | `99d69fed36ad143fa2f58f4bceaf46d2bc3088e5` | `ok` | `78aff9d2602ec6d5` | 19,972 / 707 | 0 |
| [geniuszby/pagelens](https://github.com/geniuszby/pagelens) | MoonBit hackathon | `7e2996799d585926220ee73317a03cd9bb0c3bac` | `ok` | `c9a4d043dba70bb4` | 104,589 / 3,933 | 0 |
| [guangting0905/mooncrawl](https://github.com/guangting0905/mooncrawl) | MoonBit hackathon 2026, MoonBit hackathon | `42af6a0b3a80e161682b771421c08090fea93ec3` | `ok` | `45afd28e31d92e71` | 49,106 / 1,945 | 0 |
| [JingLan0v0/moonbit-jmespath](https://github.com/JingLan0v0/moonbit-jmespath) | MoonBit hackathon | `f0df94360ef8cf15d3ea4d8668ad660d25a21c8a` | `ok` | `615bf05ab0fbae06` | 66,739 / 2,428 | 0 |
| [JJ-ai-nb/moonbit-submit-guard-clean](https://github.com/JJ-ai-nb/moonbit-submit-guard-clean) | 既有工作区候选清单 | `c61460d9bfce682ec79d3d0068071766a0cbc41d` | `ok` | `351be94b01698814` | 23,223 / 874 | 0 |
| [JQ-ai-nb/JoinWitness](https://github.com/JQ-ai-nb/JoinWitness) | MoonBit hackathon | `a7ced38fbd76b344f06b613e046ef3f6084924ec` | `ok` | `ebf48b6a3a1e743f` | 92,272 / 2,296 | 0 |
| [LING71671/moon-egui](https://github.com/LING71671/moon-egui) | 既有工作区候选清单 | `ff5c2c17deb54fe77c7d8095e6a74f63c4d0bb11` | `ok` | `15765c0bf84d0b6c` | 918,540 / 33,542 | 0 |
| [LMK-ai-nb/TideWeave](https://github.com/LMK-ai-nb/TideWeave) | MoonBit hackathon | `2a87502c6e2285b8cc37c799afeb225bbede810b` | `ok` | `592999e4f5350116` | 126,430 / 3,423 | 0 |
| [logicore-code/mbcrdt](https://github.com/logicore-code/mbcrdt) | MoonBit hackathon 2026, MoonBit hackathon | `fc19e58dc5ad94c92a42647b90d6dc215a8bcf7d` | `ok` | `d63dcf59aca68013` | 42,816 / 1,586 | 0 |
| [logicore-code/mblisp](https://github.com/logicore-code/mblisp) | MoonBit hackathon 2026, MoonBit hackathon | `ee63ab3e37f8166aa2bde9b2c267e9495d6ce3c8` | `ok` | `efae43ed6828b12c` | 62,889 / 2,214 | 0 |
| [lycvvt/mooncontrol](https://github.com/lycvvt/mooncontrol) | 既有工作区候选清单 | `c080998e3f42a194344179756d5fb12ec81f375d` | `ok` | `f8efe004f209aa3f` | 104,197 / 3,414 | 0 |
| [mw1696803-hub/moonup](https://github.com/mw1696803-hub/moonup) | MoonBit hackathon | `c87aea17d99f8229bdba8224dfc2cfbcac246547` | `ok` | `587af962d094a635` | 163,586 / 4,109 | 0 |
| [njuamiee/bse-auto-trader](https://github.com/njuamiee/bse-auto-trader) | MoonBit hackathon 2026, MoonBit hackathon | `ddf74003318b0487baaf4b25a279bf2a5d85fbc9` | `ok` | `09751cce49787cb4` | 110,380 / 4,084 | 0 |
| [Rindoncreate/petgrowth](https://github.com/Rindoncreate/petgrowth) | MoonBit 黑客松 | `d080ca459457ed7dfafd57d5cea85c4b33627ddc` | `ok` | `9eeb9f2f404a765c` | 72,059 / 2,290 | 0 |
| [sa2360/moonbit-toml](https://github.com/sa2360/moonbit-toml) | 既有工作区候选清单 | `4bbaf51d2a37428940d36447f72d172d82fada67` | `ok` | `586f3dd6175760ad` | 86,314 / 3,155 | 0 |
| [shencangsheng513/moonts](https://github.com/shencangsheng513/moonts) | MoonBit hackathon 2026, MoonBit hackathon | `8849d7cc5ad4af2f12dbc3d448104b03baa2c552` | `ok` | `f6f05e452f3f40fa` | 44,700 / 1,537 | 0 |
| [Sidney-sunny/MoonSpoof](https://github.com/Sidney-sunny/MoonSpoof) | MoonBit hackathon | `eaf6ab8d3328207d64845d21756d77b774b8bdbf` | `ok` | `7335e5bd11a193fa` | 543,604 / 10,199 | 0 |
| [Tino-hue/projdesk](https://github.com/Tino-hue/projdesk) | MoonBit hackathon | `48eef0d4a6b4ac8ed370d298a45c821c926cd129` | `ok` | `213fa6f940ea064e` | 365,904 / 10,971 | 0 |
| [walkzzz/moonbit-hackathon-2026](https://github.com/walkzzz/moonbit-hackathon-2026) | MoonBit hackathon 2026, MoonBit hackathon | `f16c6162db78659507fbcbe5e1f84e6916ee8184` | `ok` | `3364f0e4616ed13e` | 146,858 / 6,168 | 0 |
| [wch6766/moon_secure_codec](https://github.com/wch6766/moon_secure_codec) | 既有工作区候选清单 | `0c01936f19b8070dd1c63c0c8c16fd315ef4f666` | `ok` | `cba6c5314fa0cba1` | 89,941 / 3,353 | 0 |
| [wenhuang2333/Moonbit-haker](https://github.com/wenhuang2333/Moonbit-haker) | MoonBit hackathon | `5b39deca37239c43ea738da94146e86af6392f2e` | `ok` | `ba90224a25d59f36` | 1,533,305 / 43,698 | 0 |
| [wuhaiting321/moon-yaml](https://github.com/wuhaiting321/moon-yaml) | MoonBit hackathon 2026, MoonBit hackathon | `132060c4719e726db7845a2cba85fd4d2daad5f1` | `ok` | `cc43307f17815f5b` | 1,428 / 82 | 0 |
| [xianjuanzi/text_counter](https://github.com/xianjuanzi/text_counter) | MoonBit 黑客松 | `fd03a4822b9c76cbc5b1c053c8e473ae5cf0228a` | `ok` | `3ad698097ead1957` | 923 / 33 | 0 |
| [xy200303/tokencalc-mbt](https://github.com/xy200303/tokencalc-mbt) | MoonBit hackathon 2026, MoonBit hackathon | `6e6da55d03be2b5be67465658113c5ee66d89dd7` | `ok` | `123183bfdc927646` | 37,145 / 1,474 | 0 |
| [zhou506403/zhou](https://github.com/zhou506403/zhou) | MoonBit hackathon | `133d3e7adcbf23a15086c6ebe10bc1fd74d3c748` | `ok` | `5d9fcb27eb935458` | 110,498 / 4,435 | 0 |
| [zmjknn/OpenRPC.mbt](https://github.com/zmjknn/OpenRPC.mbt) | 既有工作区候选清单 | `62763c0c4270e3f6027e331c0cf67b687195ffc5` | `ok` | `e3f6c63c2881a01a` | 106,370 / 4,114 | 0 |

审计纳入的仓库源码均为公开 GitHub depth-1 克隆；所有 31 条记录的当前本地 HEAD 与清单 commit 一致（逐项记录见 head-check.json (`work/contest-2026-10-26/live-refresh-20261026/head-check.json`; local-only evidence)）。每个仓库的 README 哈希、绝对源码路径、完整树哈希和逐文件哈希保存在 `audit.json`。

## 审计方法与观察

审计工具 `scripts/source_similarity_audit.py` 只读取文本源码，不执行候选项目。它记录源码树和逐文件 SHA-256，并计算精确 token、标识符形状 token、规范化源码行、声明签名、结构签名，以及粗粒度语义线索；Python 文件才有标准库 AST 摘要。分流分数仅用于排序人工复核。

31 个候选的审计摘要见 `outputs/contest-source-audit-public-candidates-expanded/audit.md`。其中 `wenhuang2333/Moonbit-haker` 的分流分数最高约 0.0062；该分数不是赛事阈值，也不代表复制或抄袭。新增候选最高的 `zhou506403/zhou` 约 0.0029，仍只有人工复核信号。

## 未覆盖范围

- 官方报名、审核通过和最终参赛清单未在本次公开页面/报名表响应中出现；匿名表单是提交入口，不是结果列表。
- GitHub 仓库搜索按关键词召回，无法覆盖 GitLab、GitLink、其他平台、私有仓库、未写赛事关键词的公开仓库或已改名项目。GitHub code search 本次返回 HTTP 401，因此没有把它当作已完成的穷举。
- 固定的是 2026-10-26 抓取时的公开 HEAD；若组委会以其他 commit、压缩包或私有材料评审，当前哈希不代表该版本。
- `/api/v0/modules/` 是 Mooncakes 包目录，不是赛事 roster；本次网络刷新只固定目录 JSON 与关键字搜索结果，不把 3331 个模块都宣称为赛事项目。
- 静态相似性指标不能证明算法语义相同或不同、代码独立创作、版权许可充分、报名资格或组委会最终判重。

## 要求补齐的最小输入

若要真正完成赛事全量复核，需要组委会或参赛者提供带项目名称、源码 URL/归档、完整 commit 或归档 SHA-256、授权范围的官方清单。把该清单替换到 `contest-source-manifest-expanded.json` 的 `projects` 后重新运行审计，并对高分文件人工回看。没有官方清单时，扩大公开搜索只能增加候选数量，不能把结果升级为“全部参赛项目”。
