# R11 空库试用包演练

日期：2026-11-28。仓库是 `D:\Qbank`，分支 `feat/r11-trial-pack`，起点是 `origin/main` 的 `23fdfe3`（PR #116 的合并）。解释器是 conda 环境 `k12-qbank`。本页只记录这次空库演练实际打印的结果。

调用方连接串指向 `k12_d5_schema`，只用来读取主机、端口、角色和口令，并核对 `current_database()`。演练新建 `k12_r11_src` 与 `k12_r11_dst`，结束后删除。本机库 `k12` 没有被写入，也没有执行 migrate down。没有调用火山引擎，没有跑 `scripts/ai_probe.py`。夹具书号是 `synth-r11-book`。没有真实题干、真实答案、真实学生姓名或整页照片。

## 命令和结果

```text
python scripts/drill_trial_pack.py
```

退出码 0。脚本自己的 `elapsed_ms` 是 10001。标准输出：

```text
PHASE 1 ok
PHASE 2 ok
PHASE 3 ok
PHASE 4 ok
PHASE 5 ok
PHASE 6 ok
TRIAL PACK DRILL PASS migrations=20 books=1 papers=2 backup_verified=yes restored_match=yes archived=1 elapsed_ms=10001
```

演练结束后，`pg_database` 里没有 `k12_r11_src` 和 `k12_r11_dst`。本机库 `k12` 的 `schema_migrations` 仍是 V001 到 V007。已有的 `postgres` 容器保持 healthy，没有被重启。没有残留的演练 uvicorn 进程。

## 这次核对了什么

脚本在 `try ... finally` 里跑。失败也会停掉它自己启动的 uvicorn，并删除两个临时库和临时目录。通过行只在清理之后、两个临时库都已不在时打印。

1. 空库 `k12_r11_src` 以 `K12_ENV=production` 和 `K12_AI_PROVIDER=mock` 启动。`GET /health` 与 `GET /health/ready` 为 200。已应用迁移等于仓库里的 V001–V020，共 20 个。开发夹具用户、学生和 `q-v1` 都是 0 行。服务没有 `/ready` 这一条路由。
2. 引导管理员在改密前，写操作返回 `password_change_required`。改密后放行。合成三目录书先 `dry_run=true` 再写入。`written=true`。课时树能读到。
3. 管理员建立老师和学生并授权 `math`。老师核准并发布后出一份多题卷，PDF 以 `%PDF-` 开头。正式发放后，用标准库生成的最小 JPEG 收卷。mock 识别到 `succeeded`。批改至少一题采用、一题改判为 `incorrect`。`GET /api/admin/ai/accuracy` 里 `runs.succeeded` 和 `items.linked_ai` 都不小于 1。再出一份练习，`source_paper_id` 指向原卷。两份 PDF 的 SHA-256 只在进程内存里比较，不打印。
4. 停掉连接源库的进程后，用环境变量里的口令做加密联合备份。产物以 `.tar.gz.enc` 结尾，目录里没有未加密的 `.tar.gz`。`scripts/restore_trial.py --verify-only` 退出码 0，输出含 `VERIFIED`。
5. 同一份归档恢复到空库 `k12_r11_dst` 和空的文件目录。不再传入引导管理员变量，重新启动。`/health/ready` 为 200。管理员用改过后的口令登录，老师用创建时的口令登录。课时树、两份 PDF 的 SHA-256、`source_paper_id`、收卷照片字节、老师结论投影、对账计数与备份前一致。
6. 只把原卷未作废的 `teacher_decision.decided_at` 回拨 35 天。`scripts/archive_intake.py --dry-run` 打印 `confirmed=1`。正式加密归档后 `archived=1`，`--verify-archive` 打印 `ARCHIVE VERIFIED`。正在运行的恢复后服务上，该收卷照片为 410 `intake_archived`。两份 PDF 仍是 200。`GET /api/practice/papers/{id}/review` 为 200。批改页 `GET /papers/{id}/grade` 为 200。对账接口仍是 200。服务没有 `/review` 这一条路由。

口令只放在子进程环境变量里。标准输出没有连接串、备份口令、引导口令或老师口令。

## 这次没有覆盖

- R6a 的 20–50 页真实学生手写样张，以及火山引擎实测和阈值、模型拍板（`#103`，剩余 3 小时，由用户本人完成）。
- 真卷打印实拍后的版式微调（`#98`）。
- 机构操作录屏。分镜在 `docs/ops/trial-recording-script.md`，片子由用户本人录。
- 正式 CA 证书（`#28`）。
- 规模化备份策略（`#35`）。
- 外部错误接收方（`#47`）。
- 按课时自动配对（`#109`）和一次给多名学生出卷（`#110`）。

核对清单在 `docs/ops/trial-handoff-checklist.md`。
