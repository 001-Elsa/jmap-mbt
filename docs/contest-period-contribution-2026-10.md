# 2026 年 10 月本期实质贡献记录

本文件用于向评审解释当前 0.2.0 相对已发布 0.1.1 的实际变化。它不把旧的 20 个快照导入提交当作连续开发历史，也不通过拆分提交制造开发记录。

## 可核对的源码变化

当前工作区的真实改动包括：

- 删除 `src/sync/certificate.mbt` 和 `src/sync/certificate_test.mbt`，撤回通用位置证书、来源槽和独立 verifier；
- 在 `src/sync/sync.mbt` 中增加邮箱/未读视图的对象资格检查、窗口内字段失效、服务器确认后缀和 Ready-only 展示出口；
- 在 `src/jmap/api.mbt` 中增加固定四方法的 typed wire encoder，并绑定 account、ticket、查询过滤器、排序、`calculateTotal` 和显式 ID；
- 在同步核心中实现并验证 `canCalculateChanges=false` 的完整查询降级；
- 增加 JMAP wire、邮箱/未读竞态、同 queryState 补位、旧 generation、响应字段和预算边界测试；
- 更新支持范围、迁移说明、来源说明、CI 和干净归档验收，使当前发布材料不再把已撤回的证书层列为 0.2.0 能力。

## 用户可观察的行为变化

0.1.1 可以在本地序列和来源证书层做更多推导；0.2.0 明确禁止在受影响后缀上本地猜测，改为要求服务器在同一新 queryState 下返回后缀。代价是额外请求和对象重取，收益是不会把过期的邮箱属性、错误的邮箱归属或不完整的排序结果发布成 Ready。

## 当前验证

在当前工作区重新执行：

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk moon check --target wasm --deny-warn
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk moon test --target wasm --deny-warn
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
```

结果为 MoonBit wasm **75/75**、Python **27/27**。这是真实的本地工程证据；它不等于公网服务兼容、Mooncakes 0.2.0 发布或赛事验收通过。

## 开发历史边界

仓库最初的 20 个提交是在 2026-10-26 同一时间整理既有快照，不能证明逐步开发。后续提交只能记录现在开始的真实修改，不能回填旧时间、重排旧提交或制造空提交。是否接受该历史由赛事主办方决定；本文件用于如实披露，不替主办方作结论。

## 评审时应如何判断本项目

本期贡献应按“JMAP 可变查询下的有界视图收敛契约”评估，而不是按“发明了增量同步、状态机或证书”评估。RFC、CDC、集合差异、checkpoint 和独立验证都列为参考或共有机制；本项目的边界是四个固定 JMAP 方法、两条独立状态 frontier、服务器确认后缀、邮箱/未读条件和不发布错误 Ready 的组合。

