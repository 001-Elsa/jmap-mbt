# 可运行示例

首选 MoonBit 核心演示：`moon run cmd/demo --target wasm`。入口 `cmd/demo/main.mbt` 通过公共 API 完成合成 Query → Email 基线 → Get → Ready → 证书验证，检查查询顺序不受对象返回顺序影响。无需网络或凭据。

`replay_vectors.py` 是一个不联网的响应回放器。它读取 `tests/vectors/incremental_cases.json`，按事件顺序模拟有序前缀、Email/queryChanges 的增删、Email/changes 的属性更新、补位状态检查、失效恢复、预算和请求代次。运行：

```sh
python3 examples/replay_vectors.py
```

输出中的 `15/15 vectors passed` 只代表这份合成向量在参考模型中通过。它不代表 MoonBit 核心包已经通过所有目标，也不代表任何真实 JMAP 服务互操作。

`codec_roundtrip.py` 展示固定四方法 codec 的真实调用边界：从 RFC 形状的向量构造 `Email/query` 请求、解码 typed response，再编码回三元组。它只使用本地文件，运行：

```sh
python3 examples/codec_roundtrip.py
```

## 三个重点演示

1. **属性更新**（C01）：列表顺序不变，`a` 的 `keywords` 变化，仍然必须安排 `Email/get`。
2. **删除后的补位**（C02）：`[a,b,c]` 删除 `b`，按同一个 `queryState` 取回 `d`，提交 `[a,c,d]`。
3. **状态不一致拒绝**（C05）：补位响应带 `q2` 而增量已推进到 `q1`，拒绝混接并返回 `NeedsRefresh`。

其它向量覆盖 remove+add、窗口外删除、两类历史失效、窗口外进入、旧响应、调用/对象/轮数预算、能力不支持以及空/短结果。

## 对接核心引擎

核心引擎应把每次计划和响应接纳结果序列化为同一字段语义（`status`、`ordered_ids`、`query_state`、`email_state`、`reason`）。然后可以把 Python 回放输出作为独立 oracle，对比引擎的逐步 trace。对比时应保留请求代次和基准 state；只比较最终 ID 会漏掉“错误推进 token”的问题。

