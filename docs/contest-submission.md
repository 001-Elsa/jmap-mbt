> 版本边界：以下记录针对此前 0.1.x。当前本地未发布 0.2.0 已移除位置证书和本地序列归并；现行行为以 README、state-contract.md 及本轮改造报告为准，旧数量和通过项不自动适用。

# MoonJMAP 报名与验收提交材料

核对日期：2026-10-26。本人本次确认尚未提交，当前问卷提交次数为0。本文件是填写材料，**不是报名回执或审核通过证明**。

## 可直接用于表单的项目信息

- 项目名称：MoonJMAP：JMAP 有界邮件视图的保守收敛内核。
- 申报方向：新生态项目建设；个人参赛，项目此前未参赛（此前本人确认）。
- GitHub：https://github.com/001-Elsa/jmap-mbt
- Mooncakes：https://mooncakes.io/docs/001-Elsa/moonjmap ，已发布版本 `0.1.1`；当前参赛版本为本地未发布的 `0.2.0`。
- 许可证：Apache-2.0。
- Proposal：[项目申报说明](contest-proposal.md)。
- 一页说明：[项目概览](contest-one-page.md)。
- 逐项核查：[章程核查](contest-compliance-2026-10-26.md)。
- 来源与许可：[来源清单](source-provenance.md)。

项目简介：MoonJMAP以MoonBit实现只读JMAP邮件查询列表的同步内核，协调Email/changes与Email/queryChanges两条独立state，处理同queryState后缀补位、邮件对象ID归位、邮箱/未读条件失效、能力降级、预算及旧响应隔离，输出可恢复待办、下一请求或满足契约的有序前缀。主库不建立网络连接，不实现完整邮件客户端，也不提供通用证书或审计平台；通用状态机、恢复和CDC已有相关生态项目，另建理由集中于JMAP可变查询的固定协议语义和错误安全边界。

## 评审复现入口

安装MoonBit官方工具链和Python3，在仓库根目录运行：

```sh
moon check --target wasm
moon build --target wasm
moon test --target wasm
moon run cmd/demo --target wasm
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
python3 tests/verify.py --strict-structure
python3 scripts/run_differential.py
```

主示例应输出固定查询、对象按ID归位、服务器确认后缀和Ready四步；当前本地MoonBit wasm测试为75/75，Python回归为27/27。独立oracle、固定向量及有界对拍仍是有限输入证据。真实服务证据仅为此前本机Stalwart的有限记录，不能替代当前0.2.0的实服互操作验收。

源码压缩包验证：

```sh
python3 scripts/build_source_archive.py --output-dir dist
python3 scripts/release_smoke_test.py dist/moonjmap-0.2.0-src.tar.gz
python3 scripts/release_smoke_test.py dist/moonjmap-0.2.0-src.zip
```

修补后的smoke会从干净临时目录直接检查、构建、测试MoonBit主库并运行公共API示例，再执行Python、oracle和对拍。CI中的evidence job同样调用该入口。所有0.2.0改动均仍是本地未发布状态，没有把新行为冒充已包含在0.1.1线上包中。

## 必须随申报披露的事实

最初20次Git提交是在2026-10-26把既有快照按模块导入，提交使用实际整理时间；没有保存真实中间开发版本，不能以这些提交证明连续开发。详见[导入说明](repository-import.md)。章程第七章要求合理开发历史，第六章排除用拆分Commit制造虚假记录；如实披露不等于主办方已经接受。后续提交仅记录真实修改，不回填时间或改写历史。

已有Mooncakes近邻共享集合差异、恢复、CDC、前缀门禁和独立重算等机制。比较快照内未发现完整同目的实现不代表无相似或赛事判重已通过。AI协作已经披露；参赛者仍需理解和承担核心设计、来源与质量责任。

## 本人提交步骤与待办

1. 在[官方报名表](https://bxup9uklfcb.feishu.cn/share/base/form/shrcnWUMlgpbwHaXgzV7HmNhNhg)填写真实身份、联系方式及上方项目内容。个人信息、其他同时申报项目与推荐人不得推断或编造。
2. 审阅章程及报名同意条款，由本人提交。当前官网规定报名与验收均截至**2026年10月31日**，十月最多提交3次；以通过审核前最后一次有效提交或修改时间为准。
3. 加入[官方赛事群](https://work.weixin.qq.com/gm/5b6b92c8677d0555f3fb6a3f1a081399)，并将群昵称改为GitHub ID；当前是否已加入未知。
4. 保存报名回执、提交时间、有效提交次数与审核结果。报名完成不等于验收通过；对历史或相似性的评审疑问应提供原始说明和实际证据。

上述外部事实尚未闭合前，项目状态只能写“工程验收已有证据，报名未完成，历史及相似性待审”。
