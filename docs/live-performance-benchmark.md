# 真实 JMAP 服务性能基准

`scripts/real_jmap_benchmark.py` 是 MoonJMAP 的外部性能与互操作测量入口。它只对用户明确提供的 JMAP Session URL 和 Bearer 或 Basic 凭据发请求，不创建本地服务，也不把向量或 Python 投影当成网络性能证据。脚本在没有凭据、Session 返回非 2xx、能力不包含 Mail、或关键调用失败时会生成 `status=blocked`/`partial` 报告，并保持 `performance_claim=false`。

## 运行前提

需要一个有权访问邮件账号的真实 JMAP 服务，并确认该服务允许 RFC 8621 的只读方法：`Email/query`、`Email/queryChanges`、`Email/get`、`Email/changes`。把凭据放进进程环境，不要写进命令行历史、仓库或报告：

```sh
export JMAP_ACCESS_TOKEN='由服务端签发的短期 Bearer token'
export JMAP_ACCOUNT_ID='账号 id'
export JMAP_MAILBOX_ID='用于 inMailbox 的邮箱 id'
python3 scripts/real_jmap_benchmark.py \
  --session-url 'https://服务端/jmap/session' \
  --iterations 5 \
  --prefix-limit 50 \
  --max-objects 50 \
  --output outputs/real-benchmark/2026-10-26.json
```

如果本地 Stalwart 测试实例只开启 Basic 认证，可改用临时进程环境变量；脚本优先使用 Bearer，只有 Bearer 未设置时才读取 Basic，报告只记录 `scheme=basic` 和是否存在凭据：

```sh
export JMAP_BASIC_USERNAME='admin@example.test'
export JMAP_BASIC_PASSWORD='仅存在于当前进程环境的临时密码'
python3 scripts/real_jmap_benchmark.py \
  --session-url 'http://127.0.0.1:8080/.well-known/jmap' \
  --account-id 'admin@example.test' \
  --mailbox-id '<从已授权 Session/管理界面取得的邮箱 id>' \
  --allow-http --iterations 5 \
  --deployment local-real-stalwart --server-product Stalwart --server-version 0.16.27 \
  --output outputs/real-benchmark/stalwart-local-real-2026-10-26.json
```

`JMAP_ACCOUNT_ID` 缺省时，脚本会从 Session 的 `accounts` 选择 `isPersonal=true` 的账号；`JMAP_MAILBOX_ID` 不能推断，因为不同服务的 Inbox 标识不同。Session 返回的 `apiUrl` 默认作为 API 地址，必要时可用 `--api-url` 覆盖。明文 HTTP 默认拒绝，只有本地临时测试才可显式添加 `--allow-http`。

## 测量内容

每次 HTTP 调用都记录：

- HTTP 状态、单调时钟测得的 RTT（毫秒）和请求/响应字节数；
- 请求和响应 SHA-256，用于把脱敏记录与原始保管证据关联；
- 按 JMAP 方法的请求数、对象数、query `added/removed` 数和 `notFound` 数；
- 首页之外的连续前缀补位请求数；补位响应的 `queryState` 变化会计为重建边界，不会被拼接成同一前缀；
- `Email/queryChanges` 或 `Email/changes` 返回 400 时的历史重建计数；
- queryState、Email state 的哈希序列，用于检查两条 frontier 是否被错误合并。

默认每轮先请求 `Email/query(position=0)`，按 ID 分段请求 `Email/get`，从第二轮开始请求 `Email/queryChanges` 和 `Email/changes`。当 `total` 大于第一页时，默认再请求一个 `position=len(ids)` 的连续前缀页，并检查它是否仍带同一个 `queryState`；可用 `--disable-prefix-fill` 关闭这一步。该请求序列测量的是 MoonJMAP 关注的 JMAP 邮件视图边界，不能推导服务的写入吞吐或全协议性能。

## 脱敏和证据边界

输出文件只保留账号、邮箱、邮件 ID、state、请求体和响应体的哈希或计数。不会写入 Bearer token、Cookie、完整 URL 查询参数、邮件地址、主题、正文、附件或原始 JSON。`properties` 名称可以出现，因为它们是固定 RFC 投影字段，不包含用户数据。

`status=complete` 且 `performance_claim=true` 只表示：在报告记录的产品、版本、账号范围、日期和网络环境中，所有计划请求收到 2xx 响应并完成了测量。它不能推广为所有 JMAP 服务兼容，也不能替代真实互操作场景记录。应把报告与服务版本、部署位置、网络区域和数据规模一并保存，并对原始响应采用独立的受控保管策略；仓库只提交脱敏报告。

## 已完成的真实实现运行

2026-10-26 已使用 Stalwart Server v0.16.27 官方发布二进制启动临时真实服务，向合成测试账号注入 5 封邮件，并运行 5 轮固定只读场景。20/20 个 HTTP 请求返回 2xx，报告状态为 `complete`、`performance_claim=true`，结果保存在：

`outputs/real-benchmark/stalwart-local-real-20261026-seeded.json`

这是真实第三方服务实现的本机部署基准，不是 fake server 或本地模型回放。指标只代表 loopback、该 Stalwart 版本、5 封合成邮件和本次机器环境；报告不能推广为公网性能或生产 SLO。带非空 Email 对象的脱敏互操作序列保存在 `outputs/real-interop-stalwart-v0.16.27/record-seeded-object-level-20261026.json`；早期空邮箱探针仍保存在 `record-complete-20261026.json`，不应当作非空对象证据。

## 仍保留的外部托管服务阻塞记录

公开托管服务没有可用的 JMAP 账号或访问令牌。对公开 Fastmail Session URL 的无凭据探测只得到 HTTP 401，脚本因此输出 `status=blocked`、`performance_claim=false`。Stalwart v0.16.27 的本机真实实现测量已经完成并保存在上面的 seeded 报告；如果未来重新启动新的临时实例，应生成新的带版本和日期的证据文件。本地服务数据不能被表述成外部托管服务结果。

本地 `tests/test_real_jmap_benchmark.py` 使用一次性本地 HTTP 服务器检查字节、RTT、前缀补位和脱敏逻辑。这些测试只验证 harness，不应被引用为真实服务数据。
