# k12-qbank

[English](README.en.md)

机构老师用的数学题库和教学闭环。基线是 2026-11-07 的《初中数学题库与教学系统完整需求与架构设计方案》1.1。原文在 [docs/source/完整需求与架构设计方案-1.1.md](docs/source/完整需求与架构设计方案-1.1.md)。仓库里的对应说明是 [PRD.md](PRD.md)。

黑龙江省的机构老师，用人教版七年级上册有理数运算的一小批已核验题目，在电脑网页和可安装的安卓 App 上完成：核验题目、给每名学生出纸卷、收回、确认 AI 建议、再安排练习。场景是一名老师、大约 100 名学生，以后可能到大约三名老师、300 名学生。这两个数字是场景，不是容量保证。

档位是长期项目。要保存真实学情，老师会访问。文档和检查已经在仓库里。`catalog` 和 `practice` 可以在本机用合成数据走核验、出卷、打开 PDF 和确认。没有数据库。`python scripts/status.py` 只打印状态，不启动网站。

## 老师要完成的闭环

1. 练习册页面可追溯。老师核验题干、答案、解题过程和知识点。题目版本和适用答案都核准之后，才能正式出卷。
2. 按知识点、章节、题型和难度选题。给一名或多名学生生成各自的卷，打印带学号和页码的 PDF，卷面不印姓名。
3. 拍照或选图收回。缺页要提醒，补传留下历史。
4. AI 给出逐题建议和证据。老师确认、改判或手评。建议在确认之前不是正式结论。
5. 已确认的记录可以回看。老师再选原题、同类题或综合题。

已经发出的卷保留当时的题目和答案。后来改题库，不改旧卷。模型失败、看不清、缺页，都不是「学生做错」。

## 首批不做

学生在线作答，学生账号，家长账号，家长周报和月报，知识卡编辑与打印，可编辑 PPT，iOS，用手机浏览器代替安卓 App，跨机构，统一能力分，向量数据库，微服务，离线批改，以及平时绕过核验直接出卷。

## 现在的开发顺序

产品试用时，网页和安卓都要走完。写代码的顺序更窄：

1. 服务端先守住出卷和老师确认。
2. 第一段只做浏览器里的核验、出卷和确认。目录只建 `catalog` 和 `practice`。允许的切片写在 `scripts/check.conf` 的 `PHASE_SLICES`，默认就是这两项。
3. 安卓拍照、上传和缺页排在这段之后。
4. 桌面安装壳更后。等老师这台电脑上，网页已经能核验、能打开带公式的 PDF。优先试 Tauri 2 的稳定版。Electron 不是退路。

核对后的题目来自 [md-json-review](https://github.com/wisdom-km/md-json-review) 的 `.questions.json`。契约是 `k12-question-draft` 第 1 版。题库解析一次就保存，不再转成另一套题目 JSON。见 [docs/adr/0013-draft-and-geometry.md](docs/adr/0013-draft-and-geometry.md)。

参考答案还没有导入文件。扫描件、模型候选和老师修改将来共用 `k12-answer-draft` 第 1 版，来源写在 `origin`。见 [docs/adr/0014-answer-versions.md](docs/adr/0014-answer-versions.md)。

服务端和网页已采纳 Python 3.12、FastAPI、PostgreSQL、React，见 [docs/adr/0012-adopt-stack.md](docs/adr/0012-adopt-stack.md)。本机合成路径使用 FastAPI 和 React。PostgreSQL 还没连接。第一次写入题目时按 ADR 0013 建表，第一次写入答案时按 ADR 0014 建表。没有要写入的行时不建空表。安卓试用机型、安装渠道、部署地点、识别和模型供应商、备份用时、姓名遮挡的具体做法、按学科扩展时的细权限，都还没有试用数据。机构决定 DEC-01 到 DEC-06 还没填。安卓界面仍是候选。详见 [docs/adr/0010-stack-and-deploy.md](docs/adr/0010-stack-and-deploy.md) 和 [docs/adr/0011-web-and-desktop.md](docs/adr/0011-web-and-desktop.md)。

## 当前实现状态

| 部分 | 状态 |
| --- | --- |
| 文档（PRD、架构、规则、ADR、门禁） | 已完成 |
| 业务代码 `catalog` / `practice` | 合成题目上可以拒绝未核准出卷，生成单页 PDF，并按操作键确认一条作答 |
| 教学服务 | 本机合成 HTTP 和网页已接上。没有数据库，也还没有对外发布 |
| 技术栈 | Python 3.12、FastAPI、React 已锁版本。PostgreSQL 已采纳但还没连接 |
| 题目草稿导入 | 接受 `k12-question-draft` 第 1 版。内存保存。还不能出卷 |
| 答案版本 | 表和来源写在 ADR 0014。解析器和数据库都还没有 |
| 发布、知识点和多题练习 | 列写在 ADR 0015。表未建。现在一卷一题 |

## 命令

安装：Python 见 `.python-version`（3.12）。先执行 `python -m pip install -r requirements.txt`，再执行 `npm ci --prefix apps/web` 和 `npm run build --prefix apps/web`。密钥扫描另需本机 PATH 里的 gitleaks。配置见 `.env.example`，复制成 `.env` 后只留在本机。合成 HTTP 的日志在该进程的标准输出里。

启动本机合成站点（不启动数据库）：

```text
python -m uvicorn backend.bootstrap.http_app:app --host 127.0.0.1 --port 8765 --no-access-log
```

默认访问日志已关闭。带 `request_id` 的结构化日志仍打在标准输出。

浏览器打开 `http://127.0.0.1:8765/`。老师身份固定为服务端的 `teacher-synth`。启动进程会读取 `docs/fixtures/rational-number-min.json`，并把题目和答案的核准标志改成未核准。不需要另跑装载命令。第二名合成学生 `student-synth-2` 只在服务端授权里，不改夹具的六块。

服务已经在 8765 端口时，另开一个窗口执行 `python scripts/smoke_http.py`。复验：

```text
python -W error::ResourceWarning -m unittest discover -s tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
git diff --check
```

检查结果里的 `RECORD` 只表示命令写在这里。`DOCS` 只表示文档冒烟。它们都不表示教学服务已经启动，也不表示 AC-01 到 AC-09 已通过。

远端检查看 [Actions 的 check](https://github.com/wisdom-km/k12-qbank/actions)。验收入口见 [PRD 的验收](PRD.md#acceptance)：M1 是部分验证，M3 是试用验收，M4 是模型效果。

| 名称 | 命令 |
| --- | --- |
| 查看骨架状态 | `python scripts/status.py` |
| 文档冒烟 | `python scripts/smoke_docs.py` |
| 最小 core 测试 | `python -m unittest discover -s tests -v` |
| 全量检查 | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` |
| 全量检查（干净环境） | `bash scripts/check` |

## 先读

| 文件 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 给实现用的短索引和强制项 |
| [PRD.md](PRD.md) | 做什么，以及明确不做的事 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、不变量、日志、门禁 |
| [RULES.md](RULES.md) | 提交、测试和禁止事项 |
| [docs/exec-plans/active/rational-number-loop.md](docs/exec-plans/active/rational-number-loop.md) | 第一条闭环：本机合成网页。PostgreSQL 和安卓还没有 |

## 许可证

[MIT](LICENSE)。版权人 wisdom-km，2026。
