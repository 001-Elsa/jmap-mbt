# Mooncakes 0.1.0 发布记录

发布时间：2026-10-26 15:33:03（Asia/Shanghai）。

| 项目 | 已核实结果 |
| --- | --- |
| 模块 | `001-Elsa/moonjmap` |
| 版本 | `0.1.0`，未撤回 |
| 包页面 | [Mooncakes](https://mooncakes.io/docs/001-Elsa/moonjmap) |
| 发布源码 | [Git commit 6add0c4](https://github.com/001-Elsa/jmap-mbt/commit/6add0c4) |
| 正式上传 | `moon publish` 返回 HTTP 200 |
| 服务端构建 | 注册表 API 返回 `build_status=success` |
| ZIP | 72 个文件，226,422 字节 |
| ZIP SHA-256 | `3e5f8c151f95d27c26d39b46d0c90b32acf7d3152e3e04ff1f6fd0f1ce759aee` |

注册表元数据和公开下载 ZIP 均已重新读取。线上 ZIP 的 SHA-256 与发布前审查的包完全一致，包内文件也与发布源码一致。

## 安装

```sh
moon add 001-Elsa/moonjmap@0.1.0
```

三个公共包为 `001-Elsa/moonjmap/src/email`、`001-Elsa/moonjmap/src/jmap` 和 `001-Elsa/moonjmap/src/sync`。安装、导入与基本调用示例见 [README](../README.md#安装与使用)。

## 独立消费验证

在项目目录之外创建全新 MoonBit 工程，通过 `moon add` 从注册表下载精确版本，没有使用本地 path 依赖。随后调用三个公共包，检查：

- 不完整邮件对象仍被识别为不完整；
- typed JMAP 响应保留账号身份，并拒绝错误账号匹配；
- 新视图给出单个 Query 请求，起始位置为 0，默认上限为 50，generation 为 0。

消费工程的 `moon check --target wasm` 通过，`moon test --target wasm` 和 `--target wasm-gc` 均为 3/3 通过。普通静态检查中的未使用导入提示来自仅在测试中使用这些包的消费工程，不是发布包的编译错误。

## 发布前验证和范围

- 改为正式命名空间后，MoonBit wasm、wasm-gc 各 86/86 通过。
- Python 回归 26/26；MoonBit/Python 对拍 15/15。
- 本地文档生成成功；tar.gz、ZIP 源码包均通过全新目录 smoke 验收。
- `.moonignore` 排除 `work/`、`outputs/`、`dist/`、构建缓存和凭据文件；实际上传 ZIP 未包含这些目录。
- 历史调查证据保留在 GitHub，README 和文档中的相关链接已指向仓库。

本次确认了注册表发布、线上包一致性、服务端构建和真实下游安装。发布过程没有重新连接真实邮箱服务，也没有扩展此前的互操作、性能或赛事结论。
