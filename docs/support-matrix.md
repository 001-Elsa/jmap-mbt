# 本地 0.2.0 支持范围

| 能力 | 范围 |
| --- | --- |
| 邮件视图 | 单账户、指定邮箱的最新/未读、receivedAt 降序、前 N 个 ID |
| 协议方法 | Email/query、Email/queryChanges、Email/get、Email/changes 的有限投影 |
| 查询变化 | 保留不受影响的连续开头，服务器同 queryState 重新读取后缀 |
| 对象变化 | 窗口内字段失效和重取；不复制窗口外对象 |
| 展示 | Ready 时 committed_emails 按查询顺序复制完整且匹配视图的记录 |
| 恢复 | 调用方持久化 Checkpoint；请求代次、预算和错误范围检查 |
| 不交付 | SMTP/IMAP/POP3/MIME、邮件归档、发送、通用 CDC、序列 patch、位置证书、重放或来源证明平台 |

内核不建立网络连接。Python wire/probe 是适配和测试工具。本次改造用合成响应与本地测试验证；未重新验证真实邮箱或公网性能。0.2.0 本地未发布，0.1.1 发布包的能力另见其历史记录。
