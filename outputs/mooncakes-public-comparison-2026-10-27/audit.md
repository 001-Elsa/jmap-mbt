# MoonJMAP 0.2.0 Mooncakes.io 当前目录冻结与源码审计

- 捕获时间（UTC）：`2026-10-27T13:14:32.882415+00:00`
- 被审计仓库提交：`a5e3f8e3c8d37c5bb8d49bc0a17c983a009f2ef0`
- 目录原始 JSON：`/Users/hanzhen09/Desktop/jmap/work/mooncakes-snapshot-2026-10-27/modules.json`
- 目录 SHA-256：`ee999eb162cbf9b3e6268fdc6b1cb076dcaa710e14edfb841d57969497afccd9`
- 当前发布坐标：`3354` 个 `(name, version)`
- ZIP 下载成功：`3354`；失败：`0`
- manifest checksum 抽样刷新一致：`100`；不一致：`0`；读取错误：`0`；未请求：`3254`（其余坐标以下载 ZIP SHA-256 记录）
- ZIP CRC 可读源码：`3354`；未展开嵌套容器：`124` 个；源码字节：`3565408515`
- MoonJMAP 生产源码树 SHA-256：`5adbd6f3f8356f39afe75e7c733d4e190524cbd7e9de1c87e31ddcb229836a72`（`97214` bytes，3 个文件）

> 目录冻结的是 Mooncakes.io 公共发布注册表，不是赛事 roster；静态源码信号不能证明语义等价、抄袭、原创性或赛事资格。旧快照没有被本报告改日期复用。

## 当前生产源码哈希

| 文件 | bytes | SHA-256 |
|---|---:|---|
| `src/email/email.mbt` | 7500 | `6f6841c21e2c1217b882a9af186f9ae3b8503eae03d0b19dbce461406023b917` |
| `src/jmap/api.mbt` | 12403 | `6bd95c568b2c966f0971efd5e3796eb2fe3919f18bf5a6f4a1f936be60bf012e` |
| `src/sync/sync.mbt` | 77311 | `a40a4d22be900404564d2bf489bfc0a03f9d7dc2960326f6e17209d3ea01198a` |

## 全量源码读取边界

ZIP 每个可读文本源码文件均计入行、token 和规范化行集合；ZIP CRC 只在读取时校验。ZIP 内的 zip/tar/gz/xz/7z/rar 仅记录路径与字节，未展开，因此不能写成其内部源码也已比较。

| 指标 | 数量 |
|---|---:|
| 当前坐标 | 3354 |
| 成功下载 ZIP | 3354 |
| ZIP CRC 可读 | 3354 |
| 读取错误/缺失 | 0 |
| 源码文件 | 251496 |
| 源码字节 | 3565408515 |
| 未展开嵌套容器 | 124 |

## 规范信号最高的 30 个包

| 包 | 形状 token 包含率 | 规范行包含率 | 完整文件 SHA 命中 | 未展开容器 |
|---|---:|---:|---:|---:|
| `001-Elsa/moonjmap@0.1.1` | 0.8679 | 0.8969 | 0 | 0 |
| `bobzhang/openseek@0.3.2` | 0.2458 | 0.0516 | 0 | 0 |
| `moonbitlang/typst@0.1.9` | 0.2256 | 0.0527 | 0 | 0 |
| `bobzhang/mbtexcel@0.1.9` | 0.1932 | 0.0469 | 0 | 0 |
| `mizchi/ts@0.6.0` | 0.1821 | 0.0336 | 0 | 0 |
| `marianoguerra/tutuca@0.57.1` | 0.1794 | 0.0400 | 0 | 0 |
| `jtenner/starshine@0.3.0` | 0.1784 | 0.0516 | 0 | 0 |
| `hnlyxiaobing/MBOpenClacky@0.3.1` | 0.1722 | 0.0446 | 0 | 0 |
| `moonbitlang/editor@0.4.6` | 0.1655 | 0.0423 | 0 | 0 |
| `bobzhang/bap@0.4.0` | 0.1597 | 0.0365 | 0 | 0 |
| `moonbit-community/treesitter@0.1.0` | 0.1588 | 0.0382 | 0 | 0 |
| `vectie/moonclaw@0.1.6` | 0.1573 | 0.0556 | 0 | 2 |
| `ZSeanYves/markitdown@0.8.0` | 0.1553 | 0.0510 | 0 | 0 |
| `dowdiness/js_engine@0.9.0` | 0.1541 | 0.0481 | 0 | 2 |
| `Milky2018/mgstudio@0.2.1` | 0.1485 | 0.0435 | 0 | 0 |
| `moonbitlang/openseek@0.7.3` | 0.1467 | 0.0423 | 0 | 0 |
| `moonbitlang/pdflite@0.4.1` | 0.1459 | 0.0429 | 0 | 0 |
| `wzzc-dev/moui@0.2.5` | 0.1458 | 0.0469 | 0 | 0 |
| `mizchi/crater@0.19.0` | 0.1423 | 0.0400 | 0 | 0 |
| `IvanAXu/BioSeqs@0.1.9` | 0.1405 | 0.0429 | 0 | 0 |
| `f4ah6o/gpui@0.10.6` | 0.1392 | 0.0382 | 0 | 0 |
| `moonbit-community/editor@0.3.0` | 0.1352 | 0.0382 | 0 | 0 |
| `f4ah6o/dsh@0.1.28` | 0.1327 | 0.0481 | 0 | 0 |
| `bobzhang/mermaid@0.1.2` | 0.1317 | 0.0382 | 0 | 0 |
| `moonbit-community/mermaid@0.2.0` | 0.1317 | 0.0382 | 0 | 0 |
| `moonbitlang/docx2html@0.7.1` | 0.1241 | 0.0371 | 0 | 0 |
| `bobzhang/docx2html@0.5.0` | 0.1223 | 0.0348 | 0 | 0 |
| `Lampese/mathplotlib@0.18.0` | 0.1216 | 0.0365 | 0 | 0 |
| `colmugx/posoco@0.23.1` | 0.1211 | 0.0423 | 0 | 0 |
| `moonbitlang/core@0.1.20261023+d971670cd` | 0.1172 | 0.0336 | 0 | 0 |

## 判读限制

- `exact_file_hits=0` 只说明本次读取到的发布文件没有与当前三个生产文件完全相同的 SHA-256；它不是零相似或资格证明。
- token/规范行包含率只作人工复核排序；公共 API、测试样板、标准协议词汇和独立实现都会产生交集。
- 公共目录不包含未发布、私有或未登记赛事项目；审计不能替代组委会判重。
- 当前记录固定的是 0.2.0 提交后的源码树；若再次提交代码，必须重新冻结目录和重算本报告。
