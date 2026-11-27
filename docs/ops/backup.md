# 备份

开发数据和试用数据分开。本机库 `k12` 只给开发用。试用库在 `docker/compose.trial.yml` 里，默认名是 `k12_trial`。

删除真实学生数据前要人确认。能标记作废就不要物理删除。

临时夹具的文件演练仍然是：

```text
python scripts/drill_backup.py
```

它只造一份临时夹具，复制备份，再恢复到另一个临时目录并核对校验值，然后删掉夹具。这不是试用数据的备份。

试用的联合备份是 `scripts/backup_trial.py`。同一次包含 PostgreSQL 转储、`K12_FILE_DIR` 里的全部文件，以及 `manifest.json` 里的 SHA-256。默认用 OpenSSL 做 AES-256-CBC（PBKDF2）加密。口令来自环境变量 `K12_BACKUP_PASSPHRASE`，不写进命令行，也不进日志。恢复脚本是 `scripts/restore_trial.py`。它先核对全部校验值。有一项对不上就停止，不写库，也不写目录。目标库名是 `k12` 时拒绝恢复。

操作步骤见 [docs/ops/trial-deploy.md](trial-deploy.md)。备份文件放在本机 `var/backups/`（已被忽略，不进仓库）。

这次口令加密只覆盖机构试用。备份保留多久、密钥由谁管，仍没有定标。`#35` 保持打开。

收卷照片到期后的归档是另一条命令：`scripts/archive_intake.py`。它复用上面的 OpenSSL 口令和 SHA-256 核对，但只打包入选的收卷照片，不转储数据库，也不碰出卷 PDF。核对通过后才删除在线照片字节。`scripts/retention_sweep.py` 仍只清理日志、会话和登录尝试，不删照片。操作步骤见 [trial-deploy.md](trial-deploy.md) 第 9 节。归档文件放在本机 `var/archives/`（已被忽略，不进仓库）。容器里写到 `/data/logs/archives`，因为容器用户不能写 `/app/var`。
