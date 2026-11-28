# 单机试用部署

这份说明给不熟悉部署和数据库的人。目标是在这台笔记本上用 HTTPS 打开老师页，数据库和照片都在容器里。以后把同一套文件拷到云主机，换掉证书就能迁。

不要停掉 8765 上的核对页。不要停掉已经在跑的、名为 `postgres` 的容器。不要对库 `k12` 做备份或恢复。开发用的 `docker/compose.yml` 仍然只给本机数据库，这一页不改它。

下面的命令都在仓库目录 `D:\Qbank` 里执行。PowerShell 用 conda 环境 `k12-qbank`（Python 3.12）。

## 1. 生成自签证书

先看这台电脑的局域网地址。手机要连的话，把那个地址加进 `--hosts`。只在电脑自己打开时，`localhost` 和 `127.0.0.1` 就够。

```text
ipconfig
python scripts/make_trial_cert.py --hosts localhost,127.0.0.1,192.168.1.10 --out-dir var/certs
```

把 `192.168.1.10` 换成 `ipconfig` 里当前 Wi-Fi 的 IPv4。证书写到 `var/certs/server.crt` 和 `var/certs/server.key`。这个目录已被忽略。不要把这两个文件提交，也不要把私钥发到手机。已经有证书时脚本不会覆盖；要重做时加上 `--force`。`.env.trial` 里的 `K12_CERT_DIR` 保持 `../var/certs`。这个路径相对 `docker/compose.trial.yml`，指向同一个目录。不要改成 `var/certs`，compose 会把它当成卷名。

本机没有 `openssl` 时，脚本会退出并打印一条 `docker run` 命令。也可以直接加 `--via-docker`。

## 2. 填写试用环境

```text
Copy-Item .env.trial.example .env.trial
notepad .env.trial
```

至少填这几项：

| 变量 | 怎么填 |
| --- | --- |
| `K12_PG_PASSWORD` | 自己设一串较长的字母和数字。不要用 `@`、`:`、`/`、`$` |
| `K12_CORS_ORIGINS` | 和浏览器地址栏一致，例如 `https://127.0.0.1:8443`。手机访问时改成 `https://192.168.1.10:8443`。不能写 `*` |
| `K12_BOOTSTRAP_ADMIN_USERNAME` | 例如 `trial-admin`。3 到 32 位，小写字母、数字、点、下划线、连字符 |
| `K12_BOOTSTRAP_ADMIN_PASSWORD` | 至少 10 位，同时有字母和数字。只用于第一次启动 |
| `K12_AI_PROVIDER` | 先保持 `mock`。要换火山引擎时再看 `docs/ops/ai.md` |

`K12_BACKUP_PASSPHRASE` 留空。备份时在窗口里单独设，不放进容器。

`docker compose config` 会把口令展开到屏幕上。不要把那段输出贴到聊天或工单里。

## 3. 启动

```text
docker compose --env-file .env.trial -f docker/compose.trial.yml up -d --build
```

三个服务是 `postgres`、`app`、`nginx`。数据库和应用不占用宿主机的 5432 和 8765。对外只有 nginx 的 HTTPS，默认是 `https://127.0.0.1:8443`。端口可以在 `.env.trial` 里用 `K12_HTTPS_PORT` 改。

看状态：

```text
docker compose --env-file .env.trial -f docker/compose.trial.yml ps
```

`app` 要变成 healthy。第一次启动会把试用库迁到仓库里的最新版本。库名默认是 `k12_trial`。

浏览器打开 `https://127.0.0.1:8443/login`。自签证书会提示不安全。在这台试用电脑上选择继续访问。这不是正式证书。正式 CA 仍由 `#28` 跟踪，这一步不关闭它。

## 4. 首次改密

用引导管理员登录。打开 `https://127.0.0.1:8443/account`。原口令填 `.env.trial` 里的启动口令，新口令仍要至少 10 位并且同时有字母和数字。看到「口令已更新」之后，其他页面才能写入。

然后把 `.env.trial` 里的 `K12_BOOTSTRAP_ADMIN_USERNAME` 和 `K12_BOOTSTRAP_ADMIN_PASSWORD` 两行改回空，再执行：

```text
docker compose --env-file .env.trial -f docker/compose.trial.yml up -d
```

库里已经有管理员。下次启动不会再创建。

## 5. 手机连同一局域网

手机和电脑连同一个 Wi-Fi。不要用手机流量。

证书的 `--hosts` 和 `K12_CORS_ORIGINS` 都要包含电脑的局域网地址。改完后重新生成证书（加 `--force`）并重启上面的 compose。

手机浏览器打开 `https://192.168.1.10:8443/login`。系统会不信任这张自签证书。只把 `server.crt` 装到手机上，不要传 `server.key`。

- Android：把 `server.crt` 传到手机，在设置里安装 CA 证书。入口名称随系统版本不同，一般在安全和隐私、加密与凭据、安装证书。
- iPhone：用隔空投送或邮件收下 `server.crt`，安装描述文件，再到设置、通用、关于本机、证书信任设置里启用完全信任。

试用结束可以把这张证书从手机里删掉。

## 6. 换成云主机上的正式证书

把同一套仓库和 `.env.trial` 放到云主机。`K12_CORS_ORIGINS` 改成真实的 `https://域名`。向证书机构申请该域名的证书，把机构给的证书覆盖 `var/certs/server.crt`，把私钥覆盖 `var/certs/server.key`，然后只重启 nginx：

```text
docker compose --env-file .env.trial -f docker/compose.trial.yml restart nginx
```

这一步仍然不关闭 `#28`。规模化之前的证书策略还没定。

## 7. 联合加密备份

备份同时包含数据库转储、照片和卷面文件、以及每份字节的 SHA-256。口令不要写进命令，也不要写进 `.env.trial`。

```text
$env:K12_BACKUP_PASSPHRASE = "<自己设的一串口令>"
python scripts/backup_trial.py --compose-file docker/compose.trial.yml --env-file .env.trial --files-from-compose --out-dir var/backups
Remove-Item Env:K12_BACKUP_PASSPHRASE
```

窗口不回显口令。成功时打印 `BACKUP PASS` 和 `var/backups` 里的 `.tar.gz.enc`。未加密的中间文件不会留下。没有口令时脚本直接退出，不写出文件。

只检查、不写回：

```text
$env:K12_BACKUP_PASSPHRASE = "<同一串口令>"
python scripts/restore_trial.py var/backups/<刚才的文件名>.tar.gz.enc --verify-only
Remove-Item Env:K12_BACKUP_PASSPHRASE
```

成功时打印 `VERIFIED`。口令错会失败，并且不写数据库、不写文件。

恢复到试用栈时，先准备一个空目录，再执行。目标库名是 `k12` 时脚本拒绝，避免盖掉本机开发库。

```text
New-Item -ItemType Directory -Force D:\k12-trial-restore
$env:K12_FILE_DIR = "D:\k12-trial-restore"
$env:K12_PG_DATABASE = "k12_trial"
$env:K12_BACKUP_PASSPHRASE = "<同一串口令>"
python scripts/restore_trial.py var/backups/<文件名>.tar.gz.enc --compose-file docker/compose.trial.yml --env-file .env.trial --files-to-compose
Remove-Item Env:K12_BACKUP_PASSPHRASE
```

目录不是空的时候会拒绝。确认要覆盖才加 `--overwrite`。

这是这一次试用的口令加密。保留多久、密钥由谁管，仍由 `#35` 跟踪，这一步不关闭它。`scripts/drill_backup.py` 仍只演练临时夹具，不是这套备份。

## 8. 数据在哪，怎么升级

三份数据卷：

| 卷 | 内容 |
| --- | --- |
| `k12_trial_pg` | 试用库 |
| `k12_trial_files` | 卷面 PDF 和收卷照片 |
| `k12_trial_logs` | 运行日志 |

不要执行 `docker volume rm`。不要删这些卷。

升级时在仓库里拉取新代码，再构建并启动。启动时会向前迁移。不要向下迁移。

```text
docker compose --env-file .env.trial -f docker/compose.trial.yml up -d --build
```

停试用栈、但不删数据：

```text
docker compose --env-file .env.trial -f docker/compose.trial.yml down
```

不要加 `-v`。加了 `-v` 会删掉上面三份卷。

## 9. 收卷照片到期归档（R10）

全卷题目都已确认，并且最晚一条未作废结论已满 N 天，现行收卷照片才入选。被替换的旧照片在作废时间满 N 天后入选。N 来自 `K12_INTAKE_RETENTION_DAYS`，未设或不是正整数时是 30。未批完的卷不入选。出卷 PDF 不入选。老师结论、识别建议和出卷记录都不删。

命令是 `scripts/archive_intake.py`。它不由 `scripts/retention_sweep.py` 调用，因为需要口令和归档目录。没有口令时退出码 2，不写归档，不删照片。库名是 `k12` 时同样拒绝。先加密，再解密核对每个文件的 SHA-256。核对通过才标记 `intake_page.archived_at` 并删除在线照片字节。核对失败则不改库、不删字节。

已归档的照片再读，或再发起识别，返回 410 `intake_archived`。批改页和识别率对账仍可读。

本机先看数量，不写文件。连接串不要指向库名 `k12`。`K12_FILE_DIR` 必须是已有的照片目录，不能是仓库根目录。

```text
$env:K12_PG_DSN = "postgresql://k12:<口令>@127.0.0.1:5432/k12_trial"
$env:K12_FILE_DIR = "D:\k12-trial-files"
$env:K12_INTAKE_RETENTION_DAYS = "30"
python scripts/archive_intake.py --dry-run
```

正式归档。口令只放在这个窗口里，不写进 `.env.trial`，也不要贴到聊天里。成功时打印 `ARCHIVE PASS`。没有入选时也打印 `ARCHIVE PASS eligible=0 archived=0`，并且不生成空包。

```text
$env:K12_BACKUP_PASSPHRASE = "<自己设的一串口令>"
python scripts/archive_intake.py --out-dir var/archives
Remove-Item Env:K12_BACKUP_PASSPHRASE
```

事后只核对那一个包：

```text
$env:K12_BACKUP_PASSPHRASE = "<同一串口令>"
python scripts/archive_intake.py --verify-archive var/archives/<文件名>.tar.gz.enc
Remove-Item Env:K12_BACKUP_PASSPHRASE
```

成功时打印 `ARCHIVE VERIFIED`。口令错或校验失败时不改库、不删照片。

试用容器里，照片目录已经是 `/data/files`，数据库名是 `k12_trial`。容器用户不能写 `/app/var/archives`，所以输出改到日志卷 `/data/logs/archives`。先在窗口里设口令，再传进容器。`-e K12_BACKUP_PASSPHRASE` 只转发这个变量，不会把它写进编排文件。

```text
$env:K12_BACKUP_PASSPHRASE = "<自己设的一串口令>"
docker compose --env-file .env.trial -f docker/compose.trial.yml exec -T -e K12_BACKUP_PASSPHRASE app python scripts/archive_intake.py --dry-run
docker compose --env-file .env.trial -f docker/compose.trial.yml exec -T -e K12_BACKUP_PASSPHRASE app python scripts/archive_intake.py --out-dir /data/logs/archives
docker compose --env-file .env.trial -f docker/compose.trial.yml exec -T -e K12_BACKUP_PASSPHRASE app python scripts/archive_intake.py --verify-archive /data/logs/archives/<文件名>.tar.gz.enc
Remove-Item Env:K12_BACKUP_PASSPHRASE
```

这一步不关闭 `#35`。归档口令由谁保管、包保留多久，仍没有定标。

## 交给机构之前

勾选清单：[trial-handoff-checklist.md](trial-handoff-checklist.md)。操作录屏分镜：[trial-recording-script.md](trial-recording-script.md)。片子由人来录。

空库全链路演练（不写本机库 `k12`）：

```text
python scripts/drill_trial_pack.py
```

调用方的 `K12_PG_DSN` 只用来读取连接参数。脚本自己建、自己删 `k12_r11_src` 和 `k12_r11_dst`。一次实测记录在 `docs/evidence/trial-pack-drill-2026-11-28.md`。
