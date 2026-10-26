# MoonJMAP · MoonBit 入口

MoonJMAP 是 JMAP 邮件查询视图的增量一致性与恢复内核：分别跟踪邮件对象和查询顺序的 state，生成有序前缀、下一批请求和可离线验证的邮件前缀证书。网络传输由调用方负责。

完整功能、支持边界、来源和证据以 [README.md](README.md) 为准；按提交指引复现请看 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 安装与最小用法

本次交付目标版本为 `0.1.1`；先按 [验收步骤](ACCEPTANCE.md) 核对注册表实际状态。在已有 MoonBit 工程中添加该版本：

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

演示通过公共 MoonBit API 接纳合成 JMAP 响应，检查对象返回顺序 `[a,b]` 不会改变查询前缀 `[b,a]`，再检查 `Ready` 和邮件前缀证书。断言失败时以非零状态退出。真实服务兼容性及其适用范围见完整 README 中的外部记录。
