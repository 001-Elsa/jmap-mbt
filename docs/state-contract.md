# 本地 0.2.0：固定邮箱窗口状态契约

输入只支持 Latest(mailbox) 与 Unread(mailbox)，排序为 receivedAt 降序，collapseThreads=false。Email state 与 queryState 是两个独立 opaque token，只做相等比较。

对象链分页未耗尽时先继续 Email/changes。created/updated/destroyed 保持 RFC 各自含义；窗口外变化仍可要求查询重检，但不直接复制为本地邮件。窗口内 updated 立即使旧字段失效；destroyed 不再安排对象读取，查询位置由查询链处理。

queryChanges 接纳后只保留首个受影响位置之前的已知连续开头，不执行本地序列重建。其余部分使用新 queryState 的 Email/query 按 position 读取；包括 position=0 的全后缀重读。补位跨 queryState、邮件字段与固定邮箱/未读条件矛盾时要求刷新。

Ready 要求查询前缀达到 min(prefix_limit,total)，对象字段完整，查询与对象链均无未完成工作，无 pending_get，且对象满足指定邮箱与未读条件。committed_emails 额外检查 Ready 标记和这些条件，再按查询顺序复制记录。不能将 EmailView.objects 的临时内容直接当作已提交展示快照。

generation 与请求 ID 拒绝旧响应；账号、QueryKey、状态边界、请求负载及预算在接纳前检查。Checkpoint 保存同步义务，不提供服务端真实性、全局原子一致性或持久存储。标准规定的双状态流程、预算和恢复都不是原创算法主张。

## 固定 wire 请求与 total

`jmap.encode_planned_request(request, call_id)` 从核心 Plan 的一条请求生成固定四方法的 JSON envelope，检查结构化查询、账号、ticket 和负载一致。Email/query 与 Email/queryChanges 显式发送 calculateTotal=true，因为核心前缀覆盖检查需要 total。Python EmailQueryChangesRequest 与探针也提供显式 calculate_total 选项；省略时仍遵循 RFC 默认 false。

两种视图的邮箱/未读筛选均含可变属性，RFC 8620 §5.6 规定此时忽略 upToId，因此当前编码器不把该参数宣传为流量边界，也不发送它。双状态流程、calculateTotal 和上述语义都属于标准要求，不是原创贡献。
