# 项目提交指引逐项核查

核查日期：2026-10-26。按本人本次指引执行；随后本人明确“先备齐材料，暂不提交”，因此未向飞书或Gitlink大赛发送申报或个人信息。

## 0. 修改本机项目申报书

已找到`work/contest-submission/项目申报书-韩桢.md`和同目录一页说明。正式申报书已有姓名、电话、邮箱，保持原值；仅将仓库字段明确为GitHub并补Gitlink链接。一页说明只补Gitlink链接。其余正文、功能、历史说明和既有版本文字保持原样。修改前副本与字段级校验位于本机`work/submission-guide-check-2026-10-26/`。这些文件含私人联系方式，继续保存在本机，不纳入公开Git或Mooncakes。

## 1. GitHub

沿用已有公开仓库 https://github.com/001-Elsa/jmap-mbt ，没有创建重复仓库或通过网页初始化文件。新增`github` remote指向同一地址，保留`origin`。本地分支改为master并执行`git push -u github master`，GitHub默认分支已改为master；`git remote show github`及网页均确认。原main保留，不重写、删除原始历史。

新增README.mbt.md、ACCEPTANCE.md，仓库页面可见LICENSE、CI、源码和完整现有历史。交付源码提交`53ee81a`时为27次提交（含最初20次快照导入）；后续仅追加实际发布和同步核查记录，不以总次数证明历史有效。该源码的[CI 40295024732](https://github.com/001-Elsa/jmap-mbt/actions/runs/40295024732)五个job全部success，包括native实际测试。后续文档提交`62c9a4b`的[CI 40298145978](https://github.com/001-Elsa/jmap-mbt/actions/runs/40298145978)也已成功。

## 2. Gitlink

已有公开项目 https://www.gitlink.org.cn/Hzhhhh/jmap-mbt ，设置页面明确显示导入自上述GitHub项目，满足曾从GitHub导入的事实。

**已完成两端同步和默认master设置。** 改用本次临时SSH公钥完成实际Git推送，新建Gitlink的master并将保留的main快进到GitHub同名分支。两端`git ls-remote --symref`均确认默认HEAD指向master、master为`62c9a4b548a194ae8873fb72b6123867ef369f16`、main为`5c9a4687c060e39730e886697ea0eefcbbb21abb`。本记录随后追加的文档提交也需同步两端，不将上述固定核验提交冒充永远不变的最新HEAD。

独立核验禁用credential.helper、交互提示和askpass，从公开HTTPS地址重新clone Gitlink。默认分支、29条完整提交历史的顺序与集合、tree `6efeffbacbe0077bdb05a7b7ed015d4201ebda96`均与上述固定本机提交一致；README.mbt.md、LICENSE、ACCEPTANCE.md、CI和核心源码blob逐项一致。证据保存在本机`gitlink-public-clone-verification.json`。

Reposyncer曾按本人授权保存仅选择`001-Elsa/jmap-mbt`的fine-grained token（Contents/Webhooks读写、Metadata必需只读）。GitHub webhook测试ping返回204，但Gitlink服务端clone GitHub时连接中断，报`Encountered end of file`，且错误日志回显令牌。因此该令牌已撤销（GitHub刷新后无fine-grained token），Reposyncer已中止，GitHub对应webhook已停用。本次最终交付采用实际Git推送，不宣称持续自动双向同步可用。临时SSH认证仅用于本轮推送，撤销状态另记本机最终核验记录。未在公开源码、截图或本机核查证据中保留令牌值。

## 3. Mooncakes

已有账号，无需重复register/login；`moon whoami`确认为001-Elsa。已发布0.1.1，HTTP200/退出0，注册表未撤回，线上ZIP哈希与上传包一致；独立安装并调用三个公共包，all检查通过、四后端各3项消费测试通过。详情见[0.1.1发布记录](mooncakes-release-0.1.1.md)。

正式发布前全部执行了指引中的update、fmt、all检查和测试、info、package。四后端各86/86；本机Mac需要选择与Clang兼容的已有SDK：

```sh
export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk
moon fmt --check
moon check --target all --deny-warn
moon test --target all --deny-warn
moon package
```

SDKROOT只影响该shell及子进程，不修改系统配置，其他机器应选择自己的兼容SDK。源码和注册表打包分开：两个源码归档包含CI，Mooncakes工具默认不包含.github目录。发布后的核查记录是Git文档增补，不冒充已经位于上传ZIP内。

## 4. 最终核验与申报入口

本地严格命令已通过，GitHub与Gitlink均公开、默认master、已同步完整历史与文件，GitHub源码及上述文档提交CI绿色，Mooncakes 0.1.1已发布并独立安装验证。申报材料已备齐；实际报名和申报仍按本人“暂不提交”的要求保留未提交状态。源代码的实际Git历史已保留；最初快照导入的合理性和相似性仍须赛事组判断。

本人本次指定的两个入口均只查看，未填写/上传个人信息或提交：

- [飞书问卷](https://bxup9uklfcb.feishu.cn/share/base/form/shrcn2duseEVtk3e4sTRA8z5Qyf)明确显示“该问卷不在填写有效期内，无法提交”，提交按钮禁用。此页还要求身份证照片与银行卡等信息，本次未收集或上传。
- [Gitlink大赛页面](https://www.gitlink.org.cn/competitions/track1_2026MoonBit)实际为“MoonBit开源生态项目贡献赛”，显示2026-03-20至2026-07-12、报名截止7月11日、状态“已结束”。不能把它当作当前十月赛有效入口。

[十月官网](https://moonbitlang.github.io/Hackathon2026/)是另一赛期，公告截止10月31日且使用另一飞书链接；本轮没有擅自替换或向其他入口提交。后续提交前应以赛事群最新通知确认对应赛期与有效入口。

机器日志、截图、发布ZIP和字段校验证据保存在本机`work/submission-guide-check-2026-10-26/`。本核查不证明已报名、通过验收或具备奖励资格。
