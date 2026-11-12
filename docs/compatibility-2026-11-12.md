# 2026-11-12 工具链兼容性检查

检查对象：`001-Elsa/jmap-mbt` 当前源码，模块 `001-Elsa/moonjmap` 0.2.0，基于提交 `1dc6ef5151f4626de7a33b1b8c5faa3bb748197c` 加本轮兼容性修复。此记录不表示已发布新版本或已通过远端 CI。

## 实际工具链

按 https://www.moonbitlang.com/download/ 的 Unix 安装脚本安装默认 `latest`，安装位置为 `~/.moon`。更新前 moon/moonrun 为 0.1.20261012、moonc 为 v0.10.15+943464bfa；更新后 `moon version --all`：

```text
moon 0.1.20261104 (940aa18 2026-11-04) ~/.moon/bin/moon
moonc v0.10.20+65efd5b93 (2026-11-05) ~/.moon/bin/moonc
moonrun 0.1.20261104 (940aa18 2026-11-04) ~/.moon/bin/moonrun

Feature flags enabled: rr_moon_mod,rr_moon_pkg
```

已按官方 `moonbit-darwin-aarch64.sha256` 校验安装后的二进制，全部匹配。主机 Darwin arm64，Python 3.9.6，Node.js 24.19.0。

## 发现与修复

- 新工具链弃用类型声明后的 `derive(...)`，使原有 `--deny-warn` 检查失败，`moon fmt --check` 也失败。使用官方 `moon fmt` 将 `src/email/email.mbt`、`src/jmap/api.mbt`、`src/sync/sync.mbt` 中共 48 个声明迁移为前置 `#derive(...)`。没有改动同步算法或公开 API。
- 用 `moon info` 更新三个公开接口文件；归一化派生语法、`Int32`/`Int` 和 `@json.Json`/`Json` 的输出差别后，公开签名与基线一致。
- 本机默认 macOS 27.0 SDK 的 native 链接报 `tapi error: malformed file` / `unknown architecture`。指定 `SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk` 后通过。此设置是本机 SDK/链接器组合的处理方式，不应硬编码到 Linux CI。
- `moon.mod`、`moon.pkg` 格式可用；仅依赖随工具链安装的标准库，无第三方依赖需要升级。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| `moon fmt --check` | 通过 |
| wasm / wasm-gc / js / native 的 check、build（均 `--deny-warn`） | 全部通过 |
| 四后端 `moon test --target <target> --deny-warn` | 每个后端 75/75 |
| 四后端 `moon run cmd/demo --target <target>` | 全部通过；公共 API 得到 Ready，记录顺序为 `[b,a]` |
| 穷举后缀测试（包含在上述 MoonBit 测试中） | 每后端 75,140 种转移，70,952 次后缀读取 |
| Python unittest | 27/27 |
| 独立状态 oracle | 17/17，结构缺失及警告为 0 |
| Python 响应回放 | 15/15 |
| codec roundtrip 示例 | 通过 |
| MoonBit / Python 有界对拍 | 15/15 |
| tar.gz / zip 干净源码归档 | 两种归档均通过解压后的 wasm check/build/test/demo 及内置 Python/对拍检查 |
| `moon package` | 通过，仅构建本地包 |

对拍仅证明既有合成场景内的约定，不证明完整跨语言等价或实服互操作。本轮没有重跑可选的 Stalwart 网络场景。

## 复现入口与 CI

README 中的 wasm 命令为默认入口。其他后端可将 `--target wasm` 换成 `wasm-gc`、`js`、`native`；macOS native 环境限制见 README。

```sh
moon version --all
moon fmt --check
moon check --target wasm --deny-warn
moon build --target wasm --deny-warn
moon test --target wasm --deny-warn
moon run cmd/demo --target wasm
python3 scripts/run_differential.py
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
python3 tests/verify.py --strict-structure
python3 examples/replay_vectors.py
python3 examples/codec_roundtrip.py
python3 scripts/build_source_archive.py --output-dir dist
python3 scripts/release_smoke_test.py dist/moonjmap-0.2.0-src.tar.gz
python3 scripts/release_smoke_test.py dist/moonjmap-0.2.0-src.zip
moon package
```

现有 `.github/workflows/ci.yml` 已覆盖官方最新工具链安装、版本记录、四后端检查/构建/测试/示例、Python 回归、oracle、对拍、归档和包构建，因此保留原流程。CI 使用 Ubuntu、Node.js 22、Python 3.12；本轮本地结果不替代这些环境的远端运行结果。

本地完整日志在 `outputs/compatibility-2026-11-12/`，修复前失败证据在 `outputs/compatibility-2026-11-12-before-fix/`。这些日志目录按仓库既有规则忽略，不随源码提交。
