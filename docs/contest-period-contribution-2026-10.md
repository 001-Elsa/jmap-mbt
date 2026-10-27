# 2026 年 10 月本期实质贡献记录

本文件用于向评审解释当前 0.2.0 相对已发布 0.1.1 的实际变化。它不把旧的 20 个快照导入提交当作连续开发历史，也不通过拆分提交制造开发记录。

## 本期只交付三个可展示件

1. **JMAP 有界邮件视图内核**：`src/email` 与 `src/sync` 实现固定邮箱/未读视图、两条状态 frontier、窗口内对象失效、受影响位置前缀保留、同一新 `queryState` 后缀重取和 Ready-only 展示出口。
2. **可运行的四方法 wire 适配和能力降级**：`src/jmap/api.mbt` 与 Python wire 适配覆盖 `Email/query`、`Email/get`、`Email/changes`、`Email/queryChanges`，绑定账号、查询、排序、ticket、显式 ID 和 `calculateTotal`；`canCalculateChanges=false` 时完整查询降级。
3. **可复现的边界测试与真实服务互操作记录**：MoonBit/Python 边界测试和 `scripts/run_real_mutation_scenario.py`；当前 Stalwart 记录见 [mutation-scenario.md](../outputs/real-interop-stalwart-v0.16.27/mutation-scenario.md)，包含 5 封邮件、窗口内变已读、四方法响应摘要、旧 Ready 阻断、前缀截断、同新 queryState 后缀补位和最终成员资格检查。

本期材料不把通用 replay、通用证书、通用 trace、通用 CDC、通用邮件客户端或更多协议支持列为成果。

对应的当前 Mooncakes 目录冻结与源码审计见 [2026-10-27 报告](../outputs/mooncakes-public-comparison-2026-10-27/audit.md) 和 [机器摘要](../outputs/mooncakes-public-comparison-2026-10-27/snapshot.json)：3,354 个发布坐标、3,354/3,354 ZIP 可读、0 下载/读取错误、124 个未展开嵌套容器；生产源码哈希和审计提交写在报告中。

## 可核对的源码变化

当前工作区的真实改动包括：

- 在 `src/sync/sync.mbt` 中增加邮箱/未读视图的对象资格检查、窗口内字段失效、服务器确认后缀和 Ready-only 展示出口；
- 在 `src/jmap/api.mbt` 中增加固定四方法的 typed wire encoder，并绑定 account、ticket、查询过滤器、排序、`calculateTotal` 和显式 ID；
- 在同步核心中实现并验证 `canCalculateChanges=false` 的完整查询降级；
- 增加 JMAP wire、邮箱/未读竞态、同 queryState 补位、旧 generation、响应字段和预算边界测试；
- 删除 `src/sync/certificate.mbt` 和 `src/sync/certificate_test.mbt`，撤回通用位置证书、来源槽和独立 verifier；
- 增加真实 Stalwart 变更脚本和脱敏记录；更新支持范围、迁移说明、来源说明、CI 和干净归档验收。

## 用户可观察的行为变化

0.1.1 可以在本地序列和来源证书层做更多推导；0.2.0 明确禁止在受影响后缀上本地猜测，改为要求服务器在同一新 queryState 下返回后缀。代价是额外请求和对象重取，收益是不会把过期的邮箱属性、错误的邮箱归属或不完整的排序结果发布成 Ready。

## 当前验证

在当前工作区重新执行：

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk moon check --target wasm --deny-warn
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk moon test --target wasm --deny-warn
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
```

结果为 MoonBit wasm **75/75**、Python **27/27**。本机 Stalwart v0.16.27 的 0.2.0 真实变更记录也已完成：5 封邮件，四方法链全部 HTTP 2xx，旧对象未发布为 Ready，最终 `committed_emails` 为 2 个仍属于 Inbox 且未读的对象。这些是本地工程和一次实服证据；不等于所有公网服务兼容、Mooncakes 0.2.0 发布或赛事验收通过。

## 开发历史边界

仓库最初的 20 个提交是在 2026-10-26 同一时间整理既有快照，不能证明逐步开发。后续提交只能记录现在开始的真实修改，不能回填旧时间、重排旧提交或制造空提交。是否接受该历史由赛事主办方决定；本文件用于如实披露，不替主办方作结论。

## 评审时应如何判断本项目

本期贡献应按“JMAP 可变查询下的有界视图收敛契约”评估，而不是按“发明了增量同步、状态机或证书”评估。RFC、CDC、集合差异、checkpoint 和独立验证都列为参考或共有机制；本项目的边界是四个固定 JMAP 方法、两条独立状态 frontier、服务器确认后缀、邮箱/未读条件和不发布错误 Ready 的组合。

