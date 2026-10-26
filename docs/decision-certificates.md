# JMAP 邮件前缀位置证书

MoonJMAP 为一次有界邮件查询视图转移生成 `JmapEmailPrefixCertificate`（兼容类型名 `DecisionCertificate`）。当前证书用最终前缀的每个位置解释这封邮件来自旧前缀的哪个位置，或是新进入前缀的 ID；同时核查 JMAP 双 state、前缀覆盖和可选请求形状。

2026-10-26 的本地差异化重构删除了 FNV 指纹、字符串身份摘要和通用 remove/add 编辑脚本。证书直接保存结构化 `QueryKey`，请求绑定直接保存完整 `Request`，不再通过摘要代替字段比较。这是证据表示和验证算法的改变；独立验证、状态边界及完整性门禁仍是共有工程方法，不构成算法独有声明。

## 位置见证

`slots : Array[PrefixSlotWitness]` 与 `after_ids` 长度相同，每个最终位置只接受两种解释：

- `FromBefore(index)`：从不可变 `before_ids[index]` 取得邮件 ID。index 必须有效、不能重复引用，取得的 ID 必须与当前 after 位置相同。移动只改变引用位置，不构造先删再插的操作。
- `Introduced(id)`：该 ID 不在旧的有界前缀内，且必须等于当前 after ID。它只说明“新进入本地前缀”，不能推断服务器新建了一封邮件。

例如 `[a,b,c] → [b,a,x]` 的位置见证是：

```text
[FromBefore(1), FromBefore(0), Introduced("x")]
```

证书不包含通用 patch、对象字段 diff、事件链或事件重放器。旧前缀中没有被引用的 ID 自然不在新前缀内。前后 ID 的唯一性、位置引用及新进入 ID 的条件共同约束结果。

## 证书字段

- `query : QueryKey`：结构化服务、账号、Latest/Unread 邮箱视图和 `collapse_threads=false`；`QueryKey::canonical()` 仅保留为诊断显示，不能用于证书身份判断。
- before/after 有序 ID、prefix limit、total 和 `slots`。
- queryState、Email state 的 before/after 边界以及 generation。
- `Ready/Pending/NeedsRefresh/...` 完成性、原因和变化类别。
- `PrefixCoverage`：覆盖 `[0,end)`、`target_end=min(after.total,after.prefix_limit)`、缺口 `missing`、`Open/Closed` 和 `same_query_state_fill`。
- `objects_complete`：生成器检查 after 前缀的固定展示属性后记录的布尔声明。
- 可选 `EmailPrefixPlanBinding { request : Request }`：保存完整 typed 请求，包括 ticket 的结构化账号/查询、方法、代次、request ID、两个 expected state、请求 ID，及请求的分页范围、maxChanges、固定 filter/sort/properties。

结构化身份避免把包含 `|` 等分隔符的不同服务/账号拼接成相同身份。它不隐藏标识，不提供保密、签名或防伪认证。调用方应使用可公开的本地别名，不写入凭据或真实邮箱地址。

## 生成和验证

原构造函数名称保留：

```text
certificate_from_views(before, after, completeness, reason)
email_prefix_proof_from_views(before, after, completeness, reason)
certificate_from_views_with_plan(before, after, completeness, reason, plan)
certificate_from_acceptance(before, acceptance)
```

view-only 构造函数说明两个视图间的结构关系。with-plan 构造函数另外检查 plan 确为 before 视图当前允许发出的完整请求，不能仅对调用方自带字段计算一个摘要就视为请求已绑定。它只接受一个请求，复制内部可变数组，避免后续修改 plan 改变证书。

`verify_jmap_email_prefix_certificate`（兼容入口 `verify_certificate`）在 MoonBit 中：

1. 检查结构化查询、代次、总数、前缀上限和唯一非空 ID。
2. 逐最终位置解析 `FromBefore`/`Introduced`，拒绝越界、重复引用、错 ID 及把旧 ID 假称新进入。
3. 检查两条 state 的变化/消失与完成性、原因及变化类别相容。
4. 重算 coverage 区间、目标、缺口、frontier 和同 state 补位标记。
5. 检查 `objects_complete` 声明与完成性要求相容；Ready 还必须有两种 state 和关闭的前缀缺口。
6. 存在请求绑定时，逐字段检查 ticket/request 内部一致性、账号/查询、固定投影、分页区间、generation 和 before 双 state，并按四种 JMAP 方法限制允许的前缀变化。

验证器不访问网络、时钟或全局状态。它验证的是证书声明的局部结构一致性。证书不携带实际邮件字段或服务器签名，因此不能独立证明邮件内容来源、请求确实发送过、响应确实来自服务器，或所有请求读到了全局原子快照。无绑定证书也不能声称已经绑定某次网络交换。

## 旧接口迁移

此次是尚未发布的本地 0.1 源码结构调整；构造/验证函数名称仍可调用，但证书字段有不兼容变化：

| 原字段/类型 | 当前用法 |
| --- | --- |
| `query_identity`、`query_identity_digest` | 读取结构化 `certificate.query`；显示时可单独调用 `canonical()` |
| `removed`、`added`、`RemovedWitness` | 读取 `slots`；通过旧位置引用解释新位置 |
| plan binding 的扁平字段和 `request_digest` | 读取 `plan_binding.request` 与其 `ticket` |

旧证书不能只改字段名后继续使用。应从原 before/after 视图和可用计划重新生成；本项目没有提供通用旧证书转换或跨版本持久化框架。

证书仍不替代 `checkpoint`/`restore_checkpoint`。checkpoint 保存的是未完成的 JMAP 邮件同步工作；证书解释的是一次前缀转移。已撤回的原始载荷来源/trace 闭合审计层不在当前源码内。
