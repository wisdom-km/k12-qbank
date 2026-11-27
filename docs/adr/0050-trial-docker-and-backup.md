# ADR 0050 单机试用的容器、HTTPS 和联合备份

状态：accepted

## 背景

老师闭环已经能在本机进程里走完。下一次是把同一套进程放到一台笔记本上给机构试用，之后再迁到云主机。试用需要 HTTPS、独立的数据库和文件目录，以及一次能同时带走数据库和页字节的备份。

开发用的 `docker/compose.yml` 只起本机 PostgreSQL，并且发布 5432。那份文件继续给本机开发用。本机库 `k12` 不作为试用库。

## 选项

1. 改开发用的 compose，把应用和 nginx 加进去，并继续发布 5432 和 8765。
2. 另写一套试用编排。nginx 终止 TLS。应用和 PostgreSQL 只在容器网络里。宿主机只开放 HTTPS。备份把数据库转储、`K12_FILE_DIR` 和 SHA-256 清单打在一起，用口令加密。
3. 等到正式 CA 证书和备份保留策略都定下来，再做部署。

## 决定

选 2。

试用编排是 `docker/compose.trial.yml`。项目名是 `k12-trial`，不占用已经在跑的、名为 `postgres` 的容器。PostgreSQL 主版本固定为 16。库名默认 `k12_trial`。口令来自 `K12_PG_PASSWORD`，文件里不写默认口令。应用强制 `K12_ENV=production`、`K12_SESSION_SECURE=1`、`K12_OPENAPI=0`。镜像安装 `fonts-noto-cjk`。`NotoSansCJK-Regular.ttc` 落在 `pdf_font.py` 已经搜索的路径上，覆盖常用中文和圆圈序号 ① 到 ⑳。不改字体加载代码。

nginx 只监听 443，协议是 TLSv1.2 和 TLSv1.3。宿主机端口默认 8443。请求体上限 15 MiB，读超时 120 秒。反向代理增加 `Strict-Transport-Security`，不替换应用已经写出的 CSP 和 `X-Frame-Options`。

本机自签证书由 `scripts/make_trial_cert.py` 写到 `var/certs/`。证书和私钥不进仓库。这只覆盖这一次机构试用。正式 CA 仍由 `#28` 跟踪，该 issue 保持打开。

`scripts/backup_trial.py` 同一次写出数据库转储、文件字节和 `manifest.json`。默认用 `openssl enc -aes-256-cbc -pbkdf2 -salt`，口令只从环境变量 `K12_BACKUP_PASSPHRASE` 进入子进程，不出现在命令行参数里，也不写入日志。`scripts/restore_trial.py` 先核对全部 SHA-256。任一不一致就退出，不写数据库，也不写文件目录。目标库名是 `k12` 时拒绝恢复。口令加密只覆盖这一次试用。规模化的加密和保留策略仍由 `#35` 跟踪，该 issue 保持打开。

不新增迁移。不改开发用的 `docker/compose.yml`。不改 HTTP 路由和 OpenAPI。
