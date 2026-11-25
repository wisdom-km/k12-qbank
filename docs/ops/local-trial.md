# 本机试用库

这份说明给不熟悉数据库的人。目标是在本机用一个新库上课：没有合成题目，没有合成账号，可以导入真实书，给真实学生出卷。

本机已经有的库 `k12` 不要动。`k12_trial` 是另一个库。两个库的连接串只有最后的库名不同。

试用用现有的 production 模式。`K12_ENV=production` 时，启动不会读取 `docs/fixtures/rational-number-min.json`，也不会创建 `teacher-synth`、`admin-synth`、`student-synth`。不需要再加开关。本机用 HTTP 即可，这一步不要求 HTTPS。

核对页如果正听着 `127.0.0.1:8765`，不要停掉它。下面的启动命令改用别的端口，例如 `8775`。

## 1. 建一个空库

应用用角色 `k12`、口令 `changeme` 连接。这是本机示例口令，不是生产口令。角色 `k12` 在已经跑着的服务器上可能没有建库权限。建库用容器里的本地超级用户，命令里不写口令。

已经有名为 `postgres` 的容器、并且 `127.0.0.1:5432` 已经在听：

```text
docker exec -u postgres postgres psql -d postgres -c "CREATE DATABASE k12_trial OWNER k12;"
```

这台机器还没有 PostgreSQL，端口 5432 空着。在仓库里先启动一份，再在里面建试用库。这份 compose 默认还会有一个名叫 `k12` 的库。应用不要连那个库。

```text
docker compose -f docker/compose.yml up -d
docker compose -f docker/compose.yml exec -T postgres psql -U k12 -d postgres -c "CREATE DATABASE k12_trial OWNER k12;"
```

本机已经装了 `psql`，并且当前系统用户可以在维护库 `postgres` 里建库：

```text
psql -d postgres -c "CREATE DATABASE k12_trial OWNER k12;"
```

三条都只新建 `k12_trial`。不要对库 `k12` 做迁移，也不要删它。

## 2. 环境变量

在启动用的那个窗口里设置。不要把这些值写进仓库。

| 变量 | 这次试用怎么填 | 意思 |
| --- | --- | --- |
| `K12_ENV` | `production` | 不加载合成夹具，不创建合成账号 |
| `K12_PG_DSN` | `postgresql://k12:changeme@127.0.0.1:5432/k12_trial` | 只连试用库 |
| `K12_FILE_DIR` | 仓库外面的一个空目录，例如 `D:\k12-trial-files` | 卷面 PDF 和收卷照片的字节。表里只存编号和校验 |
| `K12_CORS_ORIGINS` | `http://127.0.0.1:8775` | 必须和浏览器地址栏的协议、主机、端口一致。不能是 `*`，不能空 |
| `K12_BOOTSTRAP_ADMIN_USERNAME` | 例如 `trial-admin` | 库里还没有管理员时创建一次。3 到 32 位，只能是小写字母、数字、点、下划线、连字符 |
| `K12_BOOTSTRAP_ADMIN_PASSWORD` | 自行设定，至少 10 位，同时有字母和数字 | 只用于第一次启动。首启后从窗口里清掉 |
| `K12_AI_PROVIDER` | `mock` | 不访问网络。要换火山引擎见 `docs/ops/ai.md`，三个地址、模型和密钥缺一个都会启动失败 |
| `K12_SESSION_SECURE` | `0` | 本机 HTTP 要带上会话 cookie。只有放在 HTTPS 后面才设 `1` |
| `K12_PDF_FONT_PATH` | 通常不设 | 空则用本机微软雅黑或宋体。这两套有 ① 到 ⑩，没有 ⑪ 到 ⑳。印到后面这些会 `not_rendered` |

先建目录：

```text
New-Item -ItemType Directory -Force D:\k12-trial-files
```

页面要先构建一次，同一个进程才能打开登录页、老师页、管理页、改口令页和批改页：

```text
npm run build --prefix apps/web
```

## 3. 启动、迁移、首次改密

在仓库目录 `D:\Qbank`：

```text
python -m uvicorn backend.bootstrap.http_app:app --host 127.0.0.1 --port 8775 --no-access-log
```

Python 用 conda 环境 `k12-qbank`（3.12）。首启会把这个库迁到仓库里的最新版本。窗口留着。

浏览器打开 `http://127.0.0.1:8775/login`，用引导管理员登录。登录后打开 `http://127.0.0.1:8775/account`。原口令填启动口令，新口令仍要至少 10 位并且同时有字母和数字。看到「口令已更新」之后，其他页面才能写入。没改之前，其他写入会返回 `password_change_required`。

改完之后，把 `K12_BOOTSTRAP_ADMIN_USERNAME` 和 `K12_BOOTSTRAP_ADMIN_PASSWORD` 从窗口里删掉。库里已经有管理员，下次启动不会再创建。

## 4. 导入一本书

在三个目录的上一级放 `import-book.json`。路径相对这份文件。例子：

```json
{
  "book_id": "kkl-math-7a",
  "subject_id": "math",
  "question_dir": "Seven_question",
  "answer_dir": "Seven_solution",
  "toc_dir": "Seven_catalog",
  "toc_page_offset": 0,
  "pairs": [{ "answer_page": 1, "question_page": 1 }]
}
```

预演和确认写入都会在这份清单旁边生成 `_import_reports\`。真实目录要保持只读时，先把三个目录复制到别处，把清单放在副本的上一级，不要往原目录里写。

核对页占着 8765 时，导入脚本要指向试用端口。在同一个窗口：

```text
$env:K12_IMPORT_SERVER = "http://127.0.0.1:8775"
$env:K12_IMPORT_USER = "trial-admin"
scripts\import_book.cmd --book-dir D:\某副本 --dry-run-only
```

只预演时看完报告即停，退出码 0 表示预演本身没有整本拒绝。确认写入时去掉 `--dry-run-only`，窗口问「确认写入？(y/N)」，只有 `y` 或 `Y` 会写入。规则、三种目录和报告字段见 `docs/ops/import-book.md`。

导入成功的题还没有核准。老师页里每课的可出卷题数是 0，直到逐题点「核准并发布」。

## 5. 老师、学生、授权、学号

用改过口令的管理员打开 `http://127.0.0.1:8775/admin`。

老师：用户名例如 `trial-teacher`，口令同样至少 10 位且有字母和数字。点「创建老师」。名单格式是「用户名 · 老师编号 · 状态」。老师编号是内部编号，授权时填它。

学生：学号填学校用的编号，年级例如 `g7`，学科 `math`，姓名可以空。点「创建学生」。名单格式是「学号 · 学生编号 · 状态」。授权填的是学生编号，不是学号。

授权：老师编号、学生编号、学科 `math`，点「授权」。名单里出现「有效」。

老师用自己的账号登录。出卷区的「学生」列出的是已经授权的学生编号。卷面上印的是学号。

## 6. 出卷、打印、收卷、识别、批改

老师打开 `http://127.0.0.1:8775/`。选题区按书、章、节、课时分组。点开一课，先对要用的题点「核准并发布」。再点「选中本课时全部可出卷的题」，选好学生，点「出卷」。

出现「打开 PDF」后，用浏览器打印那一页。发出去之前点「正式发放」。

收卷在老师页的「收卷」。可以拍照，也可以从相册选。步骤、缺页和手机连本机见 `docs/ops/intake.md`。

已收的照片点「AI 识别」。`K12_AI_PROVIDER=mock` 时不访问网络。换成火山引擎的变量见 `docs/ops/ai.md`。建议在老师确认之前不是成绩。

批改页是 `/papers/{卷号}/grade`，收卷区里有「批改」。采用、改判或手评见 `docs/ops/grading.md`。

## 7. 备份，以及数据在哪

备份要同时有库和文件。只有一种不算备份。

```text
docker exec postgres pg_dump -U k12 -d k12_trial -f /tmp/k12_trial.dump
docker cp postgres:/tmp/k12_trial.dump D:\k12-trial-backup\k12_trial.dump
```

再把 `D:\k12-trial-files` 整个复制到备份目录。库是 PostgreSQL 里的 `k12_trial`。卷面和照片的字节在 `K12_FILE_DIR`。仓库里没有这些数据。

不要对库 `k12` 执行 `pg_dump` 的覆盖恢复，也不要把它写进上面的连接串。

## 8. 和本机库 k12 的关系

`k12` 与 `k12_trial` 是同一台服务器上的两个库。试用的连接串以 `/k12_trial` 结尾。启动、迁移、导入、出卷都只碰到这个库。`k12` 保持原样。
