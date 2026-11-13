# 架构护栏证据

日期：2026-11-14。样例都已从工作区删掉，没有留在提交里。

## 正例

| 命令 | 退出码 | 输出 |
| --- | --- | --- |
| `python scripts/check_boundaries.py` | 0 | `LINT PASS: dependency direction, file-size cap, and first-slice scope hold.` |
| `python scripts/check_logging.py` | 0 | `M-04 PASS: logging section present; core has no print or logging-library import.` |
| `python scripts/smoke_docs.py` | 0 | `SMOKE PASS` |
| `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` | 0 | `RESULT: PASS`。gitleaks 8.30.1，历史、暂存区、工作区和未跟踪文件都干净 |

## 故意违规

每条都是写一个最小文件、跑对应命令、确认退出码 1 和编号，然后删除。

| 样例 | 命令 | 退出码 | 点名 |
| --- | --- | --- | --- |
| `backend/knowledge/` | `python scripts/check_boundaries.py` | 1 | F-13 |
| domain 里 `import fastapi` | 同上 | 1 | F-02 |
| application 导入另一切片的 domain | 同上 | 1 | F-03 |
| `backend/utils/` | 同上 | 1 | F-04 |
| kernel 文件 801 行 | 同上 | 1 | F-10 |
| 组合根 `from backend.catalog.domain import item` | 同上 | 1 | F-11 |
| `apps/android/` | 同上 | 1 | F-13 |
| `package.json` 依赖 electron | 同上 | 1 | F-13 |
| `apps/web` 导入 `backend/catalog/domain` | 同上 | 1 | F-14 |
| `logger.log(password='x')` | `python scripts/check_logging.py` | 1 | L-05 |
| `logger.log(f"failed {code}")` | 同上 | 1 | L-05 |
| kernel 里 `print` | 同上 | 1 | L-03 |
| `except Exception: pass` | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Fast` | 1 | M-05 |

报错里有改法，并指向 ARCHITECTURE 或执行计划。改法全文在 `docs/gates/HOW-TO-FIX.md`。

## 还没接到机器上的

| 规则 | 状态 |
| --- | --- |
| F-01 界面决定能否出卷 | review。还没有界面 |
| F-05、F-06 确认和旧卷快照 | review。还没有用例测试 |
| F-11 组合根里的业务分支 | review。导入 domain 已经会失败 |
| F-12 未确认就调用真实模型 | review。未落地 |
| L-01 错误只记一次、L-04 新边界有日志 | review |
| L-05 换行之后的敏感字段、照片内容 | review |
| 本机 pre-commit 钩子 | 配置在 `.pre-commit-config.yaml`。钩子调用 bash。这台电脑此前没有 bash，钩子未安装。`--fast` 本来也不跑边界和日志检查 |
| 这次新增的检查在 GitHub 上执行 | 未发生。提交还在本地时，不能写成远端已经在拦 |

## 合入门

本次没有合入 main。下表是合入前要看的项，不是「已经可以合」。

### 门禁 G2（合入）· 档位：长期 · [D] 是 · [P] 是

| 编号 | 级别 | 状态 | 证据 |
| --- | --- | --- | --- |
| M-01 | MUST | PASS | 2026-11-14 查询 `branches/main/protection`：`enforce_admins.enabled` 为 true，必需检查是 `check`，合并前要拉取请求。批准人数是 0。 |
| M-03 | MUST | PASS | 本轮没有新增密钥。远端 `secret_scanning_push_protection.status` 为 `enabled`。历史证据在 `G0-2026-11-14.md`。 |
| M-06 | MUST | FAIL | `python scripts/smoke_docs.py` 退出码 0，只证明文档还在。没有 core 单测、契约测试或端到端。脚本把 `TEST_CMD` 报成 PASS，那不能当作长期档的 M-06。 |
| M-07 | MUST | FAIL | 这次改的是门禁脚本。仓库不要求批准。还没有另一人的审查记录。 |
| M-08 | MUST | PASS | `ci.yml` 的 job 名是 `check`，并且是 main 的必需检查。运行 `43466798575` 在提交 `2eea213` 上成功。那次还不包含本文件里的新规则。 |
| M-09 | MUST | N/A | 仍没有依赖清单。有清单却没有锁文件时改为 FAIL。 |
| M-12 | MUST | PASS | 同一批改动更新了 ARCHITECTURE 的禁止表和门禁现状、ADR 0003、RULES L-05、`docs/gates/HOW-TO-FIX.md`。 |

红线：R-1 PASS。R-2 PASS（没有动真实学情）。R-3 PASS（退出码来自本轮命令，没有把未推送写成远端已强制）。

结论：未满足（M-06、M-07）。不把这次合进 main。
