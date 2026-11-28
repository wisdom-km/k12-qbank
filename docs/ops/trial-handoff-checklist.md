# 机构试用前总核对清单

交给机构试用前，由 Wisdom 逐项勾选。本页不记录测量结果，不记录口令，不记录真实学生信息。勾完后再录操作视频。录屏分镜见 [trial-recording-script.md](trial-recording-script.md)。空库演练脚本是 `scripts/drill_trial_pack.py`。

## 环境与部署

- [ ] 试用编排用 `docker/compose.trial.yml`，不要用开发用的 `docker/compose.yml` 代替。
- [ ] 自签证书只给这一次试用。浏览器会提示不受信任。正式 CA 仍是 `#28`，本项不把它标成已完成。
- [ ] `.env.trial` 只留在本机。不要提交，不要放进录屏画面。
- [ ] `docker compose --env-file .env.trial -f docker/compose.trial.yml ps` 里 nginx、app、postgres 都是 healthy。
- [ ] 首启用引导管理员登录，打开 `/account`，点「保存口令」，页面显示「口令已更新」。
- [ ] 改密成功后，从 `.env.trial` 清空 `K12_BOOTSTRAP_ADMIN_USERNAME` 和 `K12_BOOTSTRAP_ADMIN_PASSWORD`，再重启 app 容器。

## 教材准备与导入

- [ ] 在核对页把一本书导出成题目册、答案册、目录三个目录，并写出 `import-book.json`。核对页不连题库。
- [ ] 管理员打开 `/admin`，把书文件夹拖进页面，或点选择文件夹。
- [ ] 先点「预演导入」。页面应显示「预演未写入」。有拦截就先改导出，不要写入。
- [ ] 预演没有拦截后，点「确认写入」。页面应显示「已写入」。
- [ ] 老师打开 `/`，按课时逐题点「核准并发布」。按钮旁应出现「已核准并发布」。未核准的题不要出卷。

## R6a 真实样张实测关口

这一关还没做。做完之前不要把 R6a 标成已完成。步骤以 [ai-accuracy.md](ai-accuracy.md) 为准。

- [ ] 在试用库 `k12_trial` 上走 20–50 页真实学生卷：出卷、手写、拍照收卷、AI 识别、老师逐题确认。不要写进本机库 `k12`。
- [ ] 模型先对照 [ADR 0041](../adr/0041-intake-photo-and-vision.md) 确认，再跑这批样张。不要把换过模型的卷混成同一批结论。
- [ ] 管理员在 `/admin` 看「识别率对账」。用 `false_confident` 决定要不要改部署里的 `K12_AI_REVIEW_THRESHOLD`。仓库默认仍是 0.6。
- [ ] 版式不合适时，结合 `#98` 调版式参数。不要为了这一关改迁移或接口。

## 日常运维

- [ ] 每个工作日做一次加密联合备份，并立刻用 `scripts/restore_trial.py <归档> --verify-only`。成功行含 `VERIFIED`。
- [ ] 口令只放在 `K12_BACKUP_PASSPHRASE`。不要写进命令行，不要写进日志，不要写进本清单。
- [ ] 收卷照片默认满 30 天（`K12_INTAKE_RETENTION_DAYS`）后跑 `scripts/archive_intake.py`。先 `--dry-run`，再正式归档，再 `--verify-archive`。成功行含 `ARCHIVE VERIFIED`。
- [ ] 不要执行 `docker compose down -v`。那会删掉试用库的数据卷。
- [ ] 不要连接、迁移或清空本机库 `k12`。演练只用临时库，用完即删。

## 已知范围外与人工兜底

下面各项保持打开，试用时由人兜底，不要在清单上写成已完成。

- [ ] `#28` 正式 CA 证书。当前是自签。
- [ ] `#35` 规模化备份与密钥保管。当前只覆盖这一次试用的口令加密。
- [ ] `#47` 外部错误接收方。失败仍只在本机日志。
- [ ] `#98` 真卷打印实拍后的版式微调。
- [ ] `#103` R6a 的 20–50 页真实学生样张实测与阈值、模型拍板。
- [ ] `#109` 按课时自动配对答案。现在仍是核对页导出后整本导入。
- [ ] `#110` 一次给多名学生出卷。现在一张卷对应一名学生。
