# Mooncakes 0.1.1 发布记录

核查日期：2026-10-26（Asia/Shanghai）。本记录在发布后补入Git仓库，不属于已上传ZIP的成员；已发布源码提交为 `53ee81a5b4c4a527e6d1b08b82af6cf67ac5f2fa`。

| 项目 | 已核实结果 |
| --- | --- |
| 模块/版本 | `001-Elsa/moonjmap@0.1.1`，未撤回，发布后为latest |
| 发布账号 | `moon whoami` 返回 `001-Elsa` |
| 上传 | `moon publish` 返回HTTP 200，退出码0 |
| 线上ZIP | 83文件、255,374字节；已公开下载并核对 |
| SHA-256 | `fca4d2f2653b54d02cfc60c552bc5060165cf185b51b3a6d3536c96ed4648517` |
| 源码一致性 | 线上下载ZIP与发布前检查的ZIP字节哈希一致 |
| 包入口 | https://mooncakes.io/docs/001-Elsa/moonjmap |
| GitHub源码 | https://github.com/001-Elsa/jmap-mbt/commit/53ee81a5b4c4a527e6d1b08b82af6cf67ac5f2fa |

## 发布内容及验证

增加README.mbt.md、ACCEPTANCE.md和MoonBit主演示等交付文件；统一格式，保持既有主库功能与边界。仓库CI增加native执行和格式/deny-warn门禁；注册表工具不会将`.github`目录打进Mooncakes ZIP，CI由GitHub仓库提供。个人申报书和联系方式仍位于排除的本机work目录，已扫描上传ZIP确认无对应电话/邮箱，不随发布公开。

发布前`moon update`、`moon fmt --check`、`moon check --target all --deny-warn`、`moon test --target all --deny-warn`、`moon info`、`moon package`均已实际执行。四个后端各86/86。本机native使用进程级SDKROOT选择已有MacOSX26.5 SDK，未修改系统默认配置；Linux原生后端由远程CI独立运行。

[源码提交的CI](https://github.com/001-Elsa/jmap-mbt/actions/runs/40295024732)中wasm、wasm-gc、JS、native及evidence五个job全部成功。源码tar.gz和ZIP均通过干净解包验收。

在项目目录之外的新建临时工程运行`moon add 001-Elsa/moonjmap@0.1.1`，通过注册表下载精确版本。测试调用email、jmap、sync三个公共包：不完整对象判断、账号绑定和有界查询计划。`check --target all --deny-warn`通过；`test --target all --deny-warn`四后端各3/3通过，无path依赖。

`publish --dry-run`服务端返回202并写明dry-run成功、未改动，但当前CLI把202作为失败返回255；正式publish返回200/0，注册表元数据、公开下载及独立安装另行证明实际发布。未把dry-run当作发布成功。

本次不重新验证真实邮箱互操作、生产性能、原创性或赛事资格。0.1.0原版本保留，未覆盖或撤回。
