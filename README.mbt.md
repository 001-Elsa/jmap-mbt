# MoonJMAP · MoonBit 入口

当前工作区为本地未发布的 0.2.0。MoonJMAP 为固定邮箱的最新或未读邮件维护有界连续窗口，分别跟踪邮件对象和查询顺序的 state，输出下一条请求或 Ready 的有序邮件记录。受影响后缀由服务器在同一 queryState 下重新确认；位置证书与本地序列归并已移除。网络传输由调用方负责。

完整功能、支持边界、来源和证据以 [README.md](README.md) 为准；按提交指引复现请看 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 安装与最小用法

下面的新行为应从当前源码复现。Mooncakes 当前已发布的 `0.1.1` 是历史版本，见 [发布记录](docs/mooncakes-release-0.1.1.md)；以下安装命令仅用于取得该历史版本：

```sh
moon add 001-Elsa/moonjmap@0.1.1
```

为下面的独立测试，在包的 `moon.pkg` 中添加测试导入：

```moonbit nocheck
///|
import {
  "001-Elsa/moonjmap/src/email",
  "001-Elsa/moonjmap/src/sync",
} for "test"
```

在同一包中保存为 `readme_test.mbt`，再运行 `moon test --target wasm --deny-warn`。它只建立视图和查询计划，不连接邮箱。业务源码使用这些包时，应在普通 `import` 中导入：

```moonbit nocheck
///|
test "open a bounded mail view" {
  let account : @sync.AccountScope = {
    service_identity: "https://jmap.example.test",
    account_id: "account-1",
  }
  let view = @sync.open_view(
    account,
    @email.ViewSpec::Latest("inbox"),
    @sync.default_limits(),
    Some("email-state-0"),
  )
  let next = @sync.plan(view)
  assert_eq(next.requests.length(), 1)
  assert_true(next.requests[0].kind == @sync.RequestKind::Query)
}
```

## 从仓库运行核心演示

```sh
moon run cmd/demo --target wasm
```

演示通过公共 MoonBit API 接纳合成 JMAP 响应，检查对象返回顺序 `[a,b]` 不会改变查询前缀 `[b,a]`，再从 `committed_emails` 取得按查询顺序排列的 Ready 记录。断言失败时以非零状态退出。历史真实服务记录不代表本轮新协议已完成实服验证。
