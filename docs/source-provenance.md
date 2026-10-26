# 源码、规范与测试数据来源

核查日期：2026-10-26。适用范围：本仓库公开源码、合成夹具、生成适配器和随仓库交付的脱敏记录。项目许可证为 [Apache-2.0](../LICENSE)。这份清单记录可从当前材料确认的来源；作者身份、此前参赛和权利授权声明仍须由提交者本人确认。

## 实现与依赖

主功能由 `src/email/*.mbt`、`src/jmap/*.mbt`、`src/sync/*.mbt` 实现：固定邮件视图、有限 typed JMAP 模型、双 state 协调、有序前缀和领域证书。MoonBit 清单没有第三方 Mooncakes 依赖，只使用 MoonBit 标准库；[moonbitlang/core](https://github.com/moonbitlang/core) 为 Apache-2.0。Python 适配器与脚本只导入标准库和本仓库模块，不作为 MoonBit 公共依赖。

项目按 JMAP 标准设计，不以其他语言中的某个 JMAP 客户端为整库移植来源。目前公开源码中没有 vendor 目录或随库分发的第三方客户端/服务器实现。相似性调查中的第三方源码留在被排除的 `work/`，不随 Git 仓库、Mooncakes 包或源码归档分发。阅读、比较第三方项目不等于本项目取得其版权。

| 名称与链接 | 许可或使用条件 | 本项目中的范围 |
| --- | --- | --- |
| [RFC 8620](https://www.rfc-editor.org/rfc/rfc8620.html)，JSON Meta Application Protocol | IETF Trust Legal Provisions；从规范提取的 Code Components 适用规范版权段中的 Revised BSD 条件 | 请求、响应、opaque state、changes、queryChanges 和 ResultReference 的协议语义参考。测试值自行合成；未把整段 RFC 代码组件作为源代码引入。后续若提取规范代码组件，必须保留对应 BSD 通知。 |
| [RFC 8621](https://www.rfc-editor.org/rfc/rfc8621.html)，JMAP for Mail | 同上，以 RFC 文首版权声明为准 | Email 字段、过滤、排序及邮件对象方法的协议语义参考；不包含真实用户邮件。 |
| [Stalwart v0.16.27](https://github.com/stalwartlabs/stalwart/tree/v0.16.27) | 上游该版本声明 AGPL-3.0 / Stalwart Enterprise License v2 双许可，文件许可依上游各文件通知；[上游许可目录](https://github.com/stalwartlabs/stalwart/tree/v0.16.27/LICENSES) | 仅用作此前本机互操作的外部服务，被测服务不是库依赖。仓库不分发其二进制、服务源码或修改版本；没有将其代码重新许可为 Apache-2.0。 |
| [Mooncakes 近邻调查](../README.md#相似能力如何处理) | 各候选包自有许可证，以归档和对应上游为准 | 仅用于功能边界和静态相似性复核。相似机制包括 checkpoint、预算、集合差异、CDC、前缀门禁与离线重算；这些不作为独占创新主张。历史报告的来源线索不构成代码授权。 |

## 夹具、生成文件与 AI 协作

- `tests/vectors/rfc8621_vectors.json`、`incremental_cases.json` 及 MoonBit 测试中的 ID、state、地址和对象是本项目合成场景；RFC 形状用于协议对照，不是从私有邮箱导出的数据。
- `cmd/differential/main.mbt` 由 `scripts/generate_differential_adapter.py` 根据本地 `incremental_cases.json` 生成。生成器和输入在仓库中，可检查与重新生成。它不是第三方客户端代码转换产物。
- `pkg.generated.mbti` 由 `moon info` 从本项目接口生成，不是手写或第三方实现。
- `outputs/metrics/` 是固定夹具推导的合成指标；`outputs/real-*` 记录此前本机 Stalwart 与合成邮件的脱敏观测。二者不可混为公网服务或生产性能证据。公开证据的脱敏范围见 [仓库导入说明](repository-import.md)。
- 本项目使用 AI 辅助代码、测试、文档和审查，本轮修补也使用 Codex。AI 使用不代替参赛者对来源、设计和结果的责任。参赛者需要能够解释双 state、同状态补位、预算、generation 和证书验证的设计与限制。

## 发布前维护规则

新增第三方代码、图像、数据或依赖时，应在本文件记录来源、精确版本、许可证、改动与分发范围，并保留上游要求的通知。新增真实邮箱记录必须先取得授权并脱敏。当前未发现需要随分发保留但已遗漏的上游 NOTICE；这一检查只覆盖当前可见源码，不是对所有历史来源的法律保证。
