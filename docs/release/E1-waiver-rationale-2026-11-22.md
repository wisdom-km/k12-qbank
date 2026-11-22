# starlette 0.41.3 的短期 waiver

日期：2026-11-22。这不是试用，也不是 AC-01。

`pip-audit` 只有 `--ignore-vuln`，没有 waiver 文件。CI 的 deps-audit 对 `requirements.txt` 和 `pip freeze` 两条命令都显式带上下面 7 个 id。本批不升级 fastapi，也不升级 starlette。`requirements.txt` 里 starlette 仍是 0.41.3。

2026-11-22：starlette 0.41.3 一批 CVE 暂时 waive。

原因：

- 系统处于发布前，未对真实学生开放（M-14 外部仍阻塞）
- 攻击面局限在内网老师端
- 升到 starlette >= 1.3.1 是跨主版本 breaking，需要 fastapi 同步升级
- 该迁移配得上独立批次（规划 E3），不塞进 E1。规划 E3 升级 fastapi+starlette

到期日：2026-12-31。到期后此文件必须被重审，或者这些 CVE 已经修复。

到期日由 [E1-waiver-review-2026-12-31.md](E1-waiver-review-2026-12-31.md) 跟踪。issue 是 #70。

PYSEC-2026-1941
PYSEC-2026-1942
PYSEC-2026-161
PYSEC-2026-2281
PYSEC-2026-2280
PYSEC-2026-249
PYSEC-2026-248
