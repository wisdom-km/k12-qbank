# knowledge 内存目录

日期：2026-11-20。本批没有 PostgreSQL 走查，也没有新的运行日志。

## knowledge 用例

`python -m unittest discover -s tests/knowledge -v`

```text
Ran 21 tests in 0.001s
OK
```

退出码 0。覆盖建改删、综合题只能挂 support、无标签不进检索、多条方法、学科不一致，以及不存在和未核准的题目版本。

## 全量检查

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1`

```text
ok ready, smoke passed, process stopped cleaned=True
M-06  MUST   PASS   business smoke 'python -m unittest discover -s tests -v' exit 0
RESULT: PASS (machine checks that apply now)
CHECK_EXIT 0
```

`K12_PG_DSN` 未设置。没有 V006，没有 `--apply`。
