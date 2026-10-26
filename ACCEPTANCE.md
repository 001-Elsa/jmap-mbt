# MoonJMAP 项目验收

从仓库根目录运行本文命令。完整功能和边界见 [README.md](README.md)，最小 MoonBit 用法见 [README.mbt.md](README.mbt.md)，场景与预期行为见 [独立验收矩阵](tests/acceptance_matrix.md)。

本文是可执行的验收步骤，不是本次运行结果。命令必须实际返回 0 才能记为通过；保存工具链版本和输出，不能以已有工作流文件或旧提交的绿色 CI 代替当前提交验证。

## 1. 工具链与最终本地核验

准备官方 MoonBit 工具链、Python 3、Node.js（JS 后端）以及 MoonBit native 后端所需的 C 编译与链接环境。

```sh
moon version --all
git status --short
git rev-list --count HEAD
moon update
moon fmt --check
moon check --target all --deny-warn
moon test --target all --deny-warn
moon info
moon package
```

`all` 包含 native 后端。若 native 编译、链接或任一后端失败，应保留具体错误并修复；分别通过 wasm、wasm-gc、JS 或 native 静态检查，不能记成这两条 `all --deny-warn` 已通过。`moon info` 可能更新接口文件，运行后重新检查 `git status --short`，审阅变更并确保最终提交包含所需源码。

2026-10-26 的本机核验已通过 `moon check --target all --deny-warn`。本机默认 macOS 27.0 SDK 与当前 native 工具链不兼容，使用已安装的 26.5 SDK 后，全后端测试各 86 项通过：

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk moon test --target all --deny-warn
```

上述 SDK 路径只适用于本次验证的 Mac；这是单个进程的环境设置，不修改系统默认 SDK。其他 Mac 应选择与自身编译器兼容且已安装的 SDK；Linux CI 使用 Ubuntu 自身的 C 工具链，不使用这个路径。

## 2. 可运行示例与核心语义

```sh
moon run cmd/demo --target wasm
moon run cmd/demo --target wasm-gc
moon run cmd/demo --target js
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
python3 tests/verify.py --strict-structure
python3 examples/replay_vectors.py
python3 examples/codec_roundtrip.py
python3 scripts/run_differential.py
```

主演示应打印 `Ready: ordered_ids=[b, a], queryState=q0, emailState=e0` 和 `JMAP email prefix certificate verified`。独立 oracle、固定向量和有界对拍应分别全部通过。重点检查双 state 独立推进、同 queryState 补位、对象按 ID 归位、历史失效、旧代次响应、预算暂停及证书拒绝篡改的测试。Python 回放是独立模型证据；有界对拍的比较范围见 [harness 说明](docs/differential-harness.md)。

## 3. 全新解包验收

```sh
python3 scripts/build_source_archive.py --output-dir dist
package_version=$(python3 -c 'from pathlib import Path; from scripts.build_source_archive import project_metadata; print(project_metadata(Path.cwd())[1])')
python3 scripts/release_smoke_test.py "dist/moonjmap-${package_version}-src.tar.gz"
python3 scripts/release_smoke_test.py "dist/moonjmap-${package_version}-src.zip"
```

两种归档均须包含 `README.md`、`README.mbt.md`、`LICENSE`、`ACCEPTANCE.md`、CI、源码、测试及 `RELEASE-MANIFEST.json`。smoke 会在独立临时目录核验文件清单和 SHA-256，并运行 MoonBit wasm 检查、构建、测试、主演示，以及 Python 回归、oracle、示例和对拍。这个解包检查不替代第 1 节的全后端验收。

## 4. 公开交付与提交证据

- GitHub 和 Gitlink 均须公开可访问，默认分支为 `master`，分支尖端、源码及完整提交历史一致。
- GitHub 页面须显示 `README.mbt.md`、`LICENSE`、`ACCEPTANCE.md`、`.github/workflows/ci.yml` 和核心源码；Actions 须核对本次提交的实际结果。
- 使用 `git remote -v` 和 `git remote show github` 核对地址、推送分支及远端默认分支，不凭本地 remote 名称判断公开状态。
- 用 `moon whoami` 核对发布身份，并用 `moon view 001-Elsa/moonjmap@0.1.1 --json` 核对本次交付版本是否已发布；注册表状态以实际响应为准。旧版本的记录见 [0.1.0 发布说明](docs/mooncakes-release-0.1.0.md)；本地修改不会自动更新已发布包。
- 本机项目申报书只更新参赛者姓名与赛事要求的联系方式、GitHub 链接和 Gitlink 链接。表单回执和 Gitlink 参赛页面提交结果应分别保存，技术验证通过不代表已报名。

## 5. 赛事条件与证据边界

目前参赛者已确认尚未提交报名/验收问卷。最初 20 次提交来自既有源码快照的整理导入，不能作为连续开发历史的证明，详见 [仓库导入说明](docs/repository-import.md)。代码修改、如实披露和后续真实提交不能追溯补回原始开发历史；是否接受该历史和最终相似性认定，仍由主办方决定。

逐项赛事要求及未闭合事项见 [章程核查](docs/contest-compliance-2026-10-26.md)。本地测试、源码归档、公开仓库、CI、Mooncakes 发布、问卷提交和赛事审核是分别需要证据的步骤；不得相互替代。
