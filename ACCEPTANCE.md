# 本地 0.2.0 验收入口

当前功能验收覆盖固定邮箱/未读视图、对象失效、有界查询后缀、请求及状态边界、Ready 展示出口。位置证书和本地序列重建已经移除，其旧测试数量不计入当前结果。

```sh
moon fmt --check
moon check --target wasm --deny-warn
moon test --target wasm --deny-warn
moon run cmd/demo --target wasm
python3 scripts/run_differential.py
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test*.py'
python3 tests/verify.py --strict-structure
python3 scripts/build_source_archive.py --output-dir dist
python3 scripts/release_smoke_test.py dist/moonjmap-0.2.0-src.zip
```

wasm-gc、JS 与 native 应按实际运行结果另记。完整服务器列表构造的 75,140 种合法转移用于验证保留开头和同状态后缀重读，不把实现输出直接当作期望结果。旧向量对拍对中间状态差别及额外合成服务器查询作显式说明。

本轮实测记录包括当前 0.2.0 的真实服务互操作：`python3 scripts/run_real_mutation_scenario.py` 会启动临时 Stalwart，创建 5 封邮件，将窗口内对象标为已读，并验证四方法链、旧 Ready 阻断、前缀截断、新 queryState 后缀和最终成员资格；脱敏结果见 `outputs/real-interop-stalwart-v0.16.27/mutation-scenario.md`。未运行的目标、旧发布记录和其他服务结果不能替代本轮结果；本地可运行不等于已发布或赛事通过。
