# MoonJMAP 0.2.0 真实 JMAP 变更互操作记录

捕获时间：`2026-10-27T12:38:35.070861+00:00`。服务是本机 loopback 的 Stalwart `v0.16.27`，二进制 SHA-256 为 `9496e7529893a668507b353a8694c01740854b785d9c819b141439fb26caa164`。账号、邮箱、消息内容、对象 ID 和 state token 均未写入本文件；对应字段只保存 SHA-256。

## 场景

- 视图：`Unread(inbox)`，邮箱角色：Inbox，初始邮件数：`5`。
- 初始前缀：2 个对象；把窗口内第 2 个对象标记为 `$seen=true`。
- 实际方法链：`Email/query` → 空 `Email/get` 基线 → 前缀 `Email/get` → `Email/changes` → `Email/queryChanges` → 新 `queryState` 下 position=1 的后缀 `Email/query` → 后缀 `Email/get`。

## 四方法实证

| 方法 | 关键结果 |
| --- | --- |
| `Email/query` | 初始 `ids=2`、`total=5`；后缀请求 `position=1`、`ids=1`，新 queryState |
| `Email/get` | 空基线 0 个；初始前缀 2 个；后缀替换对象 1 个；均为 HTTP 2xx |
| `Email/changes` | `updated=1`、`destroyed=0`、`hasMoreChanges=false` |
| `Email/queryChanges` | `removed=1`、`added=0`、`total=4`；受影响位置为 1 |

## MoonJMAP 0.2.0 断言

- `Email/changes` 接收后旧对象不能发布为 `Ready`：`True`。
- 只保留受影响位置之前的前缀：保留 `1` 个，实际切断位置为 `1`。
- 后缀查询使用新的 queryState：`True`。
- 最终 `committed_emails` 数量为 `2`，旧已读目标不在其中，且每个对象仍属于 Inbox、没有 `$seen`：`True`。
- 动态生成的 MoonBit 驱动：`moon run cmd/real-interop --target wasm --deny-warn`；运行结果为 `complete`。

## 边界

这是一次 5 封合成邮件、本机单进程 Stalwart 的真实 HTTP/JMAP 互操作记录。它证明当前版本在该服务和该变更序列上执行了四方法和有界 Ready 门禁，不代表所有 JMAP 实现、远程部署或性能保证。重复运行应重新创建临时服务和临时凭据，不能把本记录当作持久邮箱数据。
