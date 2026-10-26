# 真实 JMAP 服务互操作记录（模板）

已按本模板完成一条真实实现记录：Stalwart Server v0.16.27 的脱敏只读序列见
`outputs/real-interop-stalwart-v0.16.27/record-seeded-object-level-20261026.json`，综合结论和
本机性能测量见 `outputs/MoonJMAP-真实服务互操作与性能验证-2026-10-26.md`。
该 JSON 是从真实性能运行的脱敏 HTTP observations 确定性派生的对象级记录；空邮箱
探针的早期记录仍保留在同目录，不能替代非空对象证据。

复制本文到带日期的记录文件后填写。只保存脱敏的请求/响应，严禁提交 OAuth、Cookie、个人地址、正文、附件或可直接访问服务的 URL。

真实服务记录的主验证对象是 MoonJMAP 的邮件查询前缀闭环：两条 state frontier、同
queryState 补位、`Email/get` 按 ID 归位、完整性门禁，以及从接纳结果生成的
`JmapEmailPrefixCertificate`（兼容 `DecisionCertificate`）。HTTP、认证和服务能力只作为外部前提记录，不作为本项目的独有功能。

## 只读探针

仓库提供 `scripts/jmap_http_probe.py`，只发出 JMAP Session `GET` 和四个固定
邮件读取方法：`Email/query`、`Email/get`、`Email/changes`、
`Email/queryChanges`。它不会创建、更新、销毁邮件，也不会发送邮件。默认拒绝
网络；必须显式传入 `--allow-network` 才会执行请求。探针只从环境变量读取
Bearer token；对于只提供 Basic Auth 的测试服务，可使用 `--basic-env` 读取
`USERNAME:PASSWORD`。两种认证不能同时配置，认证头永远不会写入记录。

先只验证 Session 能力投影：

```sh
PYTHONPATH=src python3 scripts/jmap_http_probe.py \
  --session-url "$JMAP_SESSION_URL" \
  --token-env JMAP_TOKEN \
  --record outputs/interop-$(date +%Y%m%d)-session.json \
  --session-only \
  --allow-network
```

若服务只提供 Basic Auth，先将 `USERNAME:PASSWORD` 放入环境变量，并显式禁用
默认的 Bearer 环境变量（避免机器上残留的 `JMAP_TOKEN` 造成歧义）：

```sh
export JMAP_BASIC='admin@example.test:change-me'
PYTHONPATH=src python3 scripts/jmap_http_probe.py \
  --session-url "$JMAP_SESSION_URL" \
  --token-env '' \
  --basic-env JMAP_BASIC \
  --record outputs/interop-$(date +%Y%m%d)-basic-session.json \
  --session-only \
  --allow-network
```

确认测试账号和 mailbox 后，再运行完整的只读序列。`--account-id` 可以省略，
此时探针选择 Session 的 Mail `primaryAccounts`；`--mailbox-id` 必须是测试账号
中已授权的 mailbox ID：

```sh
PYTHONPATH=src python3 scripts/jmap_http_probe.py \
  --session-url "$JMAP_SESSION_URL" \
  --token-env JMAP_TOKEN \
  --account-id "$JMAP_ACCOUNT_ID" \
  --mailbox-id "$JMAP_MAILBOX_ID" \
  --limit 20 \
  --max-changes 50 \
  --record outputs/interop-$(date +%Y%m%d)-readonly.json \
  --allow-network
```

探针会将请求和响应 JSON 中的账号、mailbox、邮件、地址、正文、主题、附件、
ID 和 opaque state 替换或稳定哈希；URL 会去掉真实 host、port、query、fragment
和 userinfo，使用 `service.invalid` 占位，动态路径段也会哈希。记录只保留方法、状态码、允许诊断的响应头、脱敏 body、
响应 SHA-256 和耗时。请在交付前用以下检查确认凭据和内容没有落盘：

```sh
rg -n 'Bearer |Authorization|Cookie|Set-Cookie|secret|password|@' \
  outputs/interop-*.json
```

如果输出包含真实 token、Cookie、邮箱地址或正文，立即删除记录并重新生成；不要
尝试对记录做人工“部分遮挡”。本地单元测试使用环回 HTTP 服务验证了请求顺序、
`{accountId}` apiUrl 展开、四种方法解码、网络默认关闭和脱敏规则；它们不构成
真实服务互操作证据。

## 服务和环境

| 字段 | 值 |
| --- | --- |
| 服务产品/版本 | `待填写` |
| 服务部署类型 | `云/自托管/测试实例` |
| 测试日期（时区） | `待填写` |
| MoonJMAP commit | `待填写` |
| 运行时/编译器版本 | `待填写` |
| 认证方式 | `仅记录类型，不记录凭据` |
| 测试邮箱 | `合成或已脱敏账号标识` |

## 能力投影

```json
{
  "maxCallsInRequest": null,
  "maxObjectsInGet": null,
  "supportsQueryChanges": null,
  "supportsEmailChanges": null,
  "supportsResultReference": null,
  "supportedFilters": [],
  "supportedSorts": []
}
```

每项都要引用原始 Session 响应的脱敏片段或说明“未提供”。不能凭产品名称推测支持矩阵。

## 场景记录

| 场景 | 请求序列 | 响应文件 | 结果 | 备注 |
| --- | --- | --- | --- | --- |
| 首次空列表 | `Email/query` | `redacted/01-query.json` | `Ready/Pending/...` | |
| 前缀补位 | `queryChanges → query → get` | `redacted/02-*.json` | | queryState 是否一致 |
| Email changes | `changes → get` | `redacted/03-*.json` | | 属性变化是否归位 |
| query history 失效 | `queryChanges` | `redacted/04-query-invalid.json` | | 是否重新 query |
| Email history 失效 | `changes` | `redacted/05-email-invalid.json` | | 是否仅重建对象 |
| 旧请求晚到 | 两个 generation | `redacted/06-stale.json` | | 是否丢弃旧响应 |
| 决策证书复核 | 视图转移后的证书 | `redacted/07-certificate.json` | `verified/rejected` | 双 state、coverage 和 plan binding 是否匹配 |

## 原始证据索引

| 文件 | SHA-256 | 脱敏方法 | 保留期限 |
| --- | --- | --- | --- |
| `redacted/...` | `待填写` | `ID/地址/正文替换规则` | `待填写` |

## 结论约束

只可写“在产品 X 的版本 Y、日期 Z、给定能力投影和场景下通过”。不能从一次服务记录推出所有 JMAP 服务兼容，也不能把本地 fixture 或模型测试写成真实互操作。

