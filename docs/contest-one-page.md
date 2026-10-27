# MoonJMAP 本地 0.2.0 概要

为指定邮箱最新/未读邮件维护一个有界连续窗口。只在两条 JMAP 状态链完成、邮件字段齐全且仍匹配视图时提供 Ready 记录；当服务端声明不能计算 query changes 时，自动退回完整查询，不伪造增量结果。

## 本期可展示的三个交付件

- **JMAP 有界邮件视图内核：** 两条状态 frontier、邮箱/未读成员资格、受影响位置之前的安全前缀、服务器确认后缀和 Ready 门禁。
- **四方法 wire 适配和能力降级：** `Email/query`、`Email/get`、`Email/changes`、`Email/queryChanges` 的可运行 typed 请求；不支持 query changes 时完整查询降级。
- **边界测试与真实服务互操作记录：** 可复现测试入口，以及本机 Stalwart 上 5 封邮件将窗口内对象标记已读后的四方法记录和最终成员资格检查。

本期不扩展通用 replay、通用证书、通用 trace、通用 CDC、通用邮件客户端或更多协议支持。变化只使受影响后缀失效，再在同 queryState 下向服务器读取；对象更新使旧字段立即失效；`committed_emails` 按查询顺序返回分离的记录。

协议组合、前缀失效和版本一致读取已有先例。每项改动后另做当前 Mooncakes 全量静态比较，不作零相似和赛事接受保证。0.2.0 尚未发布或推送；旧发布包为 0.1.1。开发历史与来源边界见 repository-import.md 和 source-provenance.md。实服记录见 [真实互操作证据](../outputs/real-interop-stalwart-v0.16.27/mutation-scenario.md)。
