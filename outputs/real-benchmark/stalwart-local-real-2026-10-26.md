# Stalwart 本地真实实现性能记录（2026-10-26）

这份记录来自官方 Stalwart Server v0.16.27 二进制的本机进程，部署标签为 `local-real-stalwart`，运行模式为 `recovery`。它不是托管邮箱服务的性能承诺，也没有把合成 fixture 计入结果。

## 可复核运行信息

| 字段 | 值 |
| --- | --- |
| 服务实现 | Stalwart Server |
| 版本 | `0.16.27` |
| 部署 | `local-real-stalwart` |
| 模式 | `recovery`（启动时显式使用 recovery mode，便于建立空测试账号） |
| JMAP Session | `http://127.0.0.1:<ephemeral-port>/.well-known/jmap` |
| 认证 | Basic；用户名/密码仅存在于启动进程环境，未写入报告 |
| 账号/邮箱 | 仅保存哈希，见 JSON 报告 |
| 测试数据 | 空邮箱，`Email/query.total=0`，收到对象数为 0 |
| 官方二进制 SHA-256 | `9496e7529893a668507b353a8694c01740854b785d9c819b141439fb26caa164` |
| 公开版本来源 | `https://github.com/stalwartlabs/stalwart/releases/tag/v0.16.27` |
| 主机 | `macOS-26.6-arm64-arm-64bit` |

启动时使用一个只包含 `RocksDb` 数据存储类型和临时数据目录的配置；数据目录及 Basic 密码在临时目录/环境中，测试结束后进程和临时目录已清理。

## 结果

机器可读原始记录：[stalwart-local-real-2026-10-26.json](stalwart-local-real-2026-10-26.json)

| 指标 | 值 |
| --- | ---: |
| `status` | `complete` |
| `performance_claim` | `true` |
| HTTP 请求尝试 | 20 |
| 2xx 响应 | 20 |
| 请求字节（应用层 JSON body） | 4495 |
| 响应字节（读取到的 JSON body） | 7867 |
| Email/query | 5 |
| Email/get | 5 |
| Email/changes | 5 |
| Email/queryChanges | 4 |
| 对象数 | 0 |
| query removed / added | 0 / 0 |
| RTT min / p50 / mean / p95 / max (ms) | 4.349 / 5.769 / 6.586500000000001 / 11.876 / 16.11 |
| query 前缀补位 | 0 |
| query 重建 | 0 |
| Email 重建 | 0 |

请求序列为：1 次 Session、5 次 `Email/query`、5 次空/有界 `Email/get`、5 次 `Email/changes`、4 次 `Email/queryChanges`。首次查询得到空前缀，后续四轮对同一 `queryState` 和 `Email state` 取空增量；由于数据集为空，没有自然发生前缀补位或重建。

## 解释边界

`performance_claim=true` 只表示这次本机 Stalwart 进程的所有计划调用收到 2xx，并完成了请求/响应体字节和 RTT 记录。它不表示 Stalwart 在真实公网、TLS、非空邮箱、并发负载或所有 JMAP 服务上达到某个性能等级，也不证明完整服务互操作。要形成更有代表性的性能曲线，还需在不泄露凭据的前提下导入固定数量的脱敏邮件，分别运行空邮箱、1k/10k 对象和并发场景，并记录 CPU、内存、磁盘和网络区域。
