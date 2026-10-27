> 版本边界：以下记录针对此前 0.1.x。当前本地未发布 0.2.0 已移除位置证书和本地序列归并；现行行为以 README、state-contract.md 及本轮改造报告为准，旧数量和通过项不自动适用。

# 赛事参赛项目源码比对操作与证据模板

这份模板用于记录 MoonJMAP 与**已获得源码快照的赛事项目**之间的源码相似性审计。它不把 Mooncakes 公开目录扫描结果扩展成赛事参赛名单，也不把静态指纹分数写成“抄袭”“原创”或“必然不判重”。

## 运行前必须收齐的材料

为每一个需要纳入范围的项目保存一个清单条目，并尽量同时保存源码归档：

```json
{
  "contest": "赛事名称和届次",
  "snapshot_date": "2026-10-26",
  "expected_count": 1,
  "roster_source_url": "https://example.invalid/official-roster",
  "official_roster_verified": false,
  "projects": [
    {
      "name": "参赛项目公开名称",
      "path": "/绝对路径/project.zip",
      "source_url": "https://github.com/example/project",
      "commit": "完整 commit SHA 或 tag",
      "license": "清单声明的许可证",
      "permission": "公开下载/参赛材料授权/其他说明"
    }
  ]
}
```

`path` 可以是目录或 ZIP；相对 `path` 按 manifest 文件所在目录解析。目录应保留 `.git` 外的工作区快照和提交信息；ZIP 应保留下载 URL、下载时间、HTTP 元数据（若可得）和 SHA-256。没有路径、提交号或可核验来源的条目仍可记录为“待补证”，但不应被写成已完成源代码比对。

`expected_count`、`roster_source_url` 和 `official_roster_verified` 只用于记录范围证据。只有赛事主办方可核验的名单和提交包才可能把数量匹配标为完整；把 `official_roster_verified` 写成 `true` 必须有外部材料可供复核，工具不会替用户推断。

## 执行

在项目根目录运行：

```sh
python3 scripts/source_similarity_audit.py \
  --project . \
  --manifest /绝对路径/contest-source-manifest.json \
  --out-dir outputs/contest-source-audit
```

也可以直接指定少量候选：

```sh
python3 scripts/source_similarity_audit.py \
  --project . \
  --candidate "team-a=/tmp/team-a.zip" \
  --candidate "team-b=/tmp/team-b" \
  --out-dir outputs/contest-source-audit
```

工具只使用 Python 标准库；它不会执行、导入或构建候选代码。ZIP 成员若含绝对路径或 `..` 路径会被拒绝。输出包括：

- `audit.json`：清单摘要、MoonJMAP 与每个候选的源码树哈希、逐文件哈希、许可证/来源线索、指纹计数和比较数据；
- `audit.md`：适合人工复核的报告，包含方法和限制；
- 每个候选是否成功读取以及失败原因。

## 比对信号

审计结果至少要同时查看四类信号：

1. **词法**：删除注释、归一化字符串和数字后，计算保留标识符的精确 token 指纹，以及将标识符替换为 `<ID>` 的形状 token 指纹。以 MoonJMAP 指纹集为分母的包含率用于发现“候选只复制了 MoonJMAP 一小部分”的情况，Jaccard 用于观察整体重合。
2. **AST（有限适用）**：Python 文件使用标准库 `ast.parse` 生成精确和标识符/字面量归一化 AST 摘要。MoonBit、Rust、JavaScript 等没有在工具内嵌入未经验证的解析器，结果会明确显示为空；不能把通用 token 形状称为 AST 等价。
3. **结构**：记录声明签名、非平凡规范化源码行，以及括号/块深度的语法形状。它们只能帮助定位人工复核文件，不能证明算法语义相同。
4. **许可证与来源**：读取 SPDX、常见许可证标记、仓库 URL、`generated from`/`upstream`/`source from` 等文本线索。它们是溯源核查入口，不是作者身份、创作时间或许可兼容性的最终证明。

生产代码、测试/fixture 和 generated/vendor 代码分开统计。测试交集会写入 `test_surface`，但不会自动提高主分流分数；比赛常见的 RFC 向量、断言样板和公共测试数据不应单独当作实现复制。generated/vendor 文件仍保留逐文件哈希和来源线索，但不进入主生产代码指纹。

`triage_score` 只用于排序人工复核，当前权重为精确 token 0.40、形状 token 0.25、规范行 0.20、声明 0.15。分数没有赛事通用阈值；独立实现可以共享语言样板，改名/重排也可以降低词法重合。

`fingerprint_examples` 保存最多 32 个共同精确 token 指纹及其两侧文件路径，供人工回到具体文件核验。指纹本身没有源码行语义，不能单独作为复制证据。

## 人工复核顺序

按分流分数从高到低打开 `audit.json` 中的具体文件哈希、提交号和来源 URL，再做以下判断：

1. 是否是同一来源、同一提交或明确允许的依赖；
2. 是否只是 MoonBit/语言运行时、RFC 示例、许可证模板或生成文件；
3. 是否存在连续的大段相同实现、相同声明与相同控制流；
4. 高分是否只由测试、例子、vendor 或通用样板造成；
5. 赛事章程采用的是主题相似、功能相似、源码复制还是依赖许可标准；
6. 把证据文件、人工结论、评审规则和不确定性分开保存。

## 不能由本审计证明的事项

- 没有完整、官方或可核验的赛事名单时，不能声称“已比对全部参赛项目”。本工具只审计 `projects` 数组和 `--candidate` 参数中的条目。
- 不能由 Mooncakes 公开包快照推断私有仓库、未公开参赛材料、历史版本、提交后的版本或其他代码托管平台的所有项目。
- 通用词法/声明/块结构指纹不能证明语义等价、算法独立性、作者身份或抄袭事实。AST 仅对成功解析的 Python 文件有效。
- 源码树、发布 ZIP 和赛事最终提交可能不同；缺少完整 commit/tag、下载时间和哈希时，结果只代表一个未固定的工作区快照。
- 许可证和来源文本不能证明第三方代码的法律许可、作者授权、创作时间或赛事资格；应由赛事规则和权利人材料单独核实。
- 报告不能替代组委会最终判重结论，也不能保证参赛后一定不被判重。

## 推荐结论措辞

可以写：

> 在本报告记录的赛事清单、源码快照、哈希和扫描方法下，未观察到达到人工复核标准的直接源码重合；相似性结论仅限已纳入的项目和快照。

不应写：

- “已证明与所有参赛项目完全不重复”；
- “绝对原创”“全球首创”；
- “一定不会被判重”；
- “Mooncakes/赛事中没有任何类似项目”。

